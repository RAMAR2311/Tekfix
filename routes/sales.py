# pyright: reportCallIssue=false
from flask import Blueprint, request, jsonify, flash, redirect, render_template, abort, url_for
from flask_login import login_required, current_user
from models import db, Product, ProductVariant, Sale, SaleDetail, SalePayment, Expense, DynamicKey, obtener_hora_bogota
from decorators import admin_required
from decimal import Decimal
from datetime import datetime, timedelta
from sqlalchemy import or_
from sqlalchemy.orm import joinedload

sales_bp = Blueprint('sales_bp', __name__)

@sales_bp.route('/api/validar-clave', methods=['POST'])
@login_required
def validar_clave():
    data = request.get_json()
    codigo = data.get('codigo', '').strip().upper()
    
    clave = DynamicKey.query.filter_by(key_code=codigo).first()
    
    if clave and clave.is_valid():
        clave.is_used = True
        db.session.commit()
        return jsonify({'success': True})
    
    return jsonify({'success': False}), 400

@sales_bp.route('/nueva', methods=['GET', 'POST'])
@login_required # Importante: Te bloqueará el acceso si no hay current_user logeado (Flask-Login)
def procesar_venta():
    if request.method == 'GET':
        return render_template('sales/nueva.html')

    """
    Se espera que los datos vengan en el cuerpo de la petición (JSON)
    Ej: {'items': [{ 'product_id': 1, 'cantidad': 2, 'precio_final': 15.50}, ...], 'metodo_pago': 'transferencia'}
    """
    data = request.get_json()
    items = data.get('items', [])
    pagos_data = data.get('pagos', [])  # array de pagos mixtos
    metodo_pago_legacy = data.get('metodo_pago', 'efectivo')  # Retrocompatibilidad
    
    if not items:
        return jsonify({'error': 'No se enviaron productos para la venta'}), 400

    # Separar ítems regulares de chips SIM
    regular_items = []
    sim_items = []
    for item in items:
        if item.get('es_sim') is True:
            sim_items.append(item)
        else:
            regular_items.append(item)

    # Calcular montos de cada tipo de item
    total_regulares_monto = Decimal('0.00')
    for item in regular_items:
        cantidad = int(item.get('cantidad', 0))
        precio = Decimal(str(item.get('precio_final', '0.00')))
        total_regulares_monto += (precio * cantidad)

    total_sims_monto = Decimal('0.00')
    for item in sim_items:
        precio = Decimal(str(item.get('precio_final', '0.00')))
        total_sims_monto += precio

    # Comisión por pago con tarjeta (opcional 5%)
    comision_tarjeta = Decimal(str(data.get('comision_tarjeta', '0.00')))
    if comision_tarjeta < 0:
        comision_tarjeta = Decimal('0.00')

    total_regulares_monto += comision_tarjeta
    total_cart_monto = total_regulares_monto + total_sims_monto

    # Procesar pagos recibidos
    if not pagos_data:
        pagos_data = [{'metodo_pago': metodo_pago_legacy, 'monto': None}]

    pagos_procesados = []
    total_pagos = Decimal('0.00')
    for pago_info in pagos_data:
        metodo = pago_info.get('metodo_pago', 'efectivo')
        monto_pago = pago_info.get('monto')
        
        if monto_pago is None:
            monto_pago = total_cart_monto
        else:
            monto_pago = Decimal(str(monto_pago))
        
        if monto_pago <= 0:
            raise ValueError(f"El monto del pago por '{metodo}' debe ser mayor a 0.")
        
        pagos_procesados.append({'metodo_pago': metodo, 'monto': monto_pago})
        total_pagos += monto_pago

    # Validar que la suma de pagos cubra el total exacto del carrito
    if total_pagos != total_cart_monto:
        raise ValueError(f"La suma de los pagos (${total_pagos}) no coincide con el total de la venta (${total_cart_monto}). Diferencia: ${total_cart_monto - total_pagos}.")

    try:
        # Determinar el método de pago principal
        if len(pagos_procesados) == 1:
            metodo_pago_principal = pagos_procesados[0]['metodo_pago']
        else:
            metodo_pago_principal = 'mixto'

        # Manejar Fecha de Venta para registros de fechas anteriores
        fecha_venta_str = data.get('fecha_venta')
        fecha_venta_obj = obtener_hora_bogota()
        if fecha_venta_str:
            try:
                fecha_seleccionada = datetime.strptime(fecha_venta_str, '%Y-%m-%d').date()
                if fecha_seleccionada != fecha_venta_obj.date():
                    # Si no es hoy, combinamos la fecha seleccionada con la hora actual para conservar secuencialidad de hora de registro
                    fecha_venta_obj = datetime.combine(fecha_seleccionada, fecha_venta_obj.time())
            except ValueError:
                pass # Fallback silencioso a la hora actual si el formato falla

        # Crear la venta general (su monto_total incluye productos regulares y comisión tarjeta)
        nueva_venta = Sale(
            vendedor_id=current_user.id,
            monto_total=total_regulares_monto,
            metodo_pago=metodo_pago_principal,
            fecha_venta=fecha_venta_obj,
            comision_tarjeta=comision_tarjeta
        )
        db.session.add(nueva_venta)
        db.session.flush()

        # Descontar el valor de las SIMs de los pagos para registrar pagos de venta regular
        restante_a_descontar = total_sims_monto
        pagos_regulares_datos = []
        for p in pagos_procesados:
            m_reg = p['monto']
            if restante_a_descontar > 0:
                descuento = min(m_reg, restante_a_descontar)
                m_reg -= descuento
                restante_a_descontar -= descuento
            if m_reg > 0:
                pagos_regulares_datos.append({'metodo_pago': p['metodo_pago'], 'monto': m_reg})

        # 1. Registrar productos del inventario regular
        for item in regular_items:
            product_id = item.get('product_id')
            variant_id = item.get('variant_id') # Posible variante
            cantidad_vendida = int(item.get('cantidad', 0))
            precio_venta_final = Decimal(str(item.get('precio_final', '0.00')))
            es_manual = item.get('es_manual', False)

            if cantidad_vendida <= 0:
                raise ValueError("La cantidad vendida debe ser mayor a 0.")

            if es_manual:
                # Producto manual (prestado de otro local) — no descuenta stock
                nombre_manual = item.get('nombre_manual', 'Producto Externo')
                precio_costo_manual = Decimal(str(item.get('precio_costo', '0.00')))

                detalle = SaleDetail(
                    sale_id=nueva_venta.id,
                    product_id=None,
                    variant_id=None,
                    cantidad_vendida=cantidad_vendida,
                    precio_venta_final=precio_venta_final,
                    nombre_manual=nombre_manual,
                    precio_costo_manual=precio_costo_manual
                )
                db.session.add(detalle)

                # Crear el gasto automático para descontar el ingreso prestado del balance final
                if precio_costo_manual > 0:
                    gasto_externo = Expense(
                        usuario_id=current_user.id,
                        tipo_gasto='Gasto Diario',
                        categoria='Pago Prod. Externo',
                        descripcion=f"Pago por producto manual prestado: {nombre_manual}",
                        monto=(precio_costo_manual * cantidad_vendida),
                        fecha_gasto=fecha_venta_obj
                    )
                    db.session.add(gasto_externo)
            else:
                # Producto del inventario propio
                producto = Product.query.with_for_update().get(product_id)
                
                if not producto:
                    raise ValueError(f"El producto con ID {product_id} no existe.")

                if variant_id:
                    variante = ProductVariant.query.with_for_update().get(variant_id)
                    if not variante:
                        raise ValueError(f"La variante con ID {variant_id} no existe.")
                    if cantidad_vendida > variante.cantidad_stock:
                        raise ValueError(f"Stock insuficiente para la variante '{variante.nombre_variante}' de '{producto.nombre}'. Solicitado: {cantidad_vendida}, Disponible: {variante.cantidad_stock}.")
                    variante.cantidad_stock -= cantidad_vendida
                    # El vendedor solo puede bajar del precio sugerido con aprobación. El admin tiene el costo como límite físico.
                    precio_limite_autorizado = variante.precio_costo if current_user.rol == 'admin' else (variante.precio_sugerido or producto.precio_sugerido)
                else:
                    if cantidad_vendida > producto.cantidad_stock:
                        raise ValueError(f"Stock insuficiente para el producto '{producto.nombre}'. Solicitado: {cantidad_vendida}, Disponible: {producto.cantidad_stock}.")
                    producto.cantidad_stock -= cantidad_vendida
                    # El vendedor solo puede bajar del precio sugerido con aprobación.
                    precio_limite_autorizado = producto.precio_costo if current_user.rol == 'admin' else producto.precio_sugerido

                if precio_venta_final < precio_limite_autorizado:
                    # Sistema nuevo: buscar aprobación remota aprobada y aún no consumida
                    from models import PriceApproval
                    aprobacion = None
                    if item.get('aprobacion_id'):
                        aprobacion = PriceApproval.query.filter_by(
                            id=item.get('aprobacion_id'),
                            vendedor_id=current_user.id,
                            estado='aprobado'
                        ).first()
                    
                    if not aprobacion:
                        aprobacion = PriceApproval.query.filter_by(
                            vendedor_id=current_user.id,
                            product_id=producto.id,
                            variant_id=variant_id,
                            estado='aprobado',
                            fue_vendido=False
                        ).order_by(PriceApproval.fecha_resolucion.desc()).first()

                    # Validar si existe aprobación y si el precio coincide o es superior al aprobado
                    if aprobacion and precio_venta_final >= float(aprobacion.precio_aprobado):
                        # Se permite la venta con el precio y se vincula la aprobación a la venta
                        aprobacion.venta_id = nueva_venta.id
                        aprobacion.fue_vendido = True
                        aprobacion.fecha_venta = obtener_hora_bogota()
                    else:
                        # Fallback al sistema viejo (códigos) para compatibilidad o error directo
                        auth = item.get('autorizacion')
                        if auth:
                            clave = DynamicKey.query.filter_by(key_code=auth).first()
                            if not clave or not clave.is_used:
                                raise ValueError(f"Código de autorización inválido para el producto '{producto.nombre}'.")
                        else:
                            raise ValueError(f"No autorizado: El precio solicitado (${precio_venta_final}) para '{producto.nombre}' requiere aprobación del administrador.")

                detalle = SaleDetail(
                    sale_id=nueva_venta.id,
                    product_id=producto.id,
                    variant_id=variant_id,
                    cantidad_vendida=cantidad_vendida,
                    precio_venta_final=precio_venta_final
                )
                db.session.add(detalle)

        # 2. Registrar venta independiente de SIMs asociadas
        for item in sim_items:
            sim_id = item.get('product_id')
            precio_venta_real = Decimal(str(item.get('precio_final', '0.00')))
            
            from models import SimCard
            sim = SimCard.query.with_for_update().get(sim_id)
            if not sim:
                raise ValueError(f"La SIM con ID {sim_id} no existe.")
            if sim.estado == 'Vendida':
                raise ValueError(f"La SIM con número {sim.numero_telefono} ya fue vendida previamente.")
                
            sim.estado = 'Vendida'
            sim.vendedor_id = current_user.id
            sim.precio_venta_real = precio_venta_real
            sim.metodo_pago = pagos_procesados[0]['metodo_pago'] if pagos_procesados else 'efectivo'
            sim.fecha_venta = fecha_venta_obj
            sim.sale_id = nueva_venta.id

        # 3. Registrar los pagos proporcionales de productos regulares
        for pago_info in pagos_regulares_datos:
            pago = SalePayment(
                sale_id=nueva_venta.id,
                metodo_pago=pago_info['metodo_pago'],
                monto=pago_info['monto']
            )
            db.session.add(pago)

        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': 'Venta registrada e inventario descontado con éxito.',
            'sale_id': nueva_venta.id,
            'total': str(total_cart_monto)
        }), 201

    except ValueError as val_err:
        db.session.rollback()
        return jsonify({'error': str(val_err)}), 400
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Ocurrió un error interno al procesar la venta.'}), 500

# Endpoint API asíncrono para el escáner del Punto de Venta
@sales_bp.route('/api/producto/<path:sku>', methods=['GET'])
@login_required
def api_buscar_producto(sku):
    producto = Product.query.filter_by(sku=sku, tipo_inventario='tienda', activo=True).first()
    
    if not producto:
        # Intentar buscar chip SIM disponible con este SKU (ICCID)
        from models import SimCard
        sim = SimCard.query.filter_by(iccid=sku, estado='Disponible').first()
        if sim:
            return jsonify({
                'id': sim.id,
                'nombre': f"[SIM {sim.operador.upper()}] {sim.numero_telefono}",
                'sku': sim.iccid,
                'cantidad_stock': 1,
                'precio_minimo': float(sim.precio_costo),
                'precio_limite': float(sim.precio_costo) if current_user.rol == 'admin' else float(sim.precio_venta),
                'precio_sugerido': float(sim.precio_venta),
                'es_sim': True,
                'variantes': []
            })
        return jsonify({'error': 'Código SKU no encontrado en el sistema'}), 404
        
    return jsonify({
        'id': producto.id,
        'nombre': producto.nombre,
        'sku': producto.sku,
        'cantidad_stock': producto.total_stock,
        'precio_minimo': float(producto.precio_minimo),
        # El límite operativo para el vendedor es el sugerido; si quiere menos, pide permiso.
        'precio_limite': float(producto.precio_costo) if current_user.rol == 'admin' else float(producto.precio_sugerido),
        'precio_sugerido': float(producto.precio_sugerido),
        'variantes': [{"id": v.id, "nombre": v.nombre_variante, "stock": v.cantidad_stock, "precio_minimo": float(v.precio_minimo or producto.precio_minimo), "precio_limite": float(v.precio_costo or producto.precio_costo) if current_user.rol == 'admin' else float(v.precio_sugerido or producto.precio_sugerido), "precio_sugerido": float(v.precio_sugerido or producto.precio_sugerido)} for v in producto.variantes]
    })

def normalize_search_str(text):
    if not text:
        return ""
    import unicodedata
    nfkd = unicodedata.normalize('NFKD', str(text))
    return "".join([c for c in nfkd if not unicodedata.combining(c)]).lower().strip()

def score_product_search(q_norm, nombre, sku, variantes=None):
    if not q_norm:
        return 999
    nom_norm = normalize_search_str(nombre)
    sku_norm = normalize_search_str(sku)

    # Nivel 0: Coincidencia idéntica exacta
    if sku_norm == q_norm or nom_norm == q_norm:
        return 0
    # Nivel 1: Nombre empieza directamente con la letra/término buscado (Iniciales de producto)
    if nom_norm.startswith(q_norm):
        return 1
    # Nivel 2: SKU empieza directamente con el término
    if sku_norm.startswith(q_norm):
        return 2
    # Nivel 3: Alguna palabra del nombre empieza con el término (Iniciales de cualquier palabra)
    words = nom_norm.split()
    if any(w.startswith(q_norm) for w in words):
        return 3
    # Nivel 4: Alguna variante empieza con el término
    if variantes:
        for v in variantes:
            v_name = normalize_search_str(getattr(v, 'nombre_variante', '') or (v.get('nombre', '') if isinstance(v, dict) else str(v)))
            if v_name.startswith(q_norm) or any(w.startswith(q_norm) for w in v_name.split()):
                return 4
    # Nivel 5: El término está contenido en cualquier parte del SKU
    if q_norm in sku_norm:
        return 5
    # Nivel 6: El término está contenido en cualquier parte del nombre
    if q_norm in nom_norm:
        return 6
    # Nivel 7: El término está contenido en alguna variante
    if variantes:
        for v in variantes:
            v_name = normalize_search_str(getattr(v, 'nombre_variante', '') or (v.get('nombre', '') if isinstance(v, dict) else str(v)))
            if q_norm in v_name:
                return 7
    return 999

@sales_bp.route('/api/productos/search', methods=['GET'])
@login_required
def api_search_productos():
    query_str = request.args.get('q', '').strip()
    if not query_str or len(query_str) < 1:
        return jsonify([])
    
    q_norm = normalize_search_str(query_str)
    search_term = f"%{query_str}%"

    # Buscar también productos cuyas variantes coincidan con el término
    var_matches = ProductVariant.query.filter(
        ProductVariant.nombre_variante.ilike(search_term)
    ).limit(60).all()
    variant_prod_ids = [v.product_id for v in var_matches]

    filter_conditions = [
        Product.sku.ilike(search_term),
        Product.nombre.ilike(search_term)
    ]
    if variant_prod_ids:
        filter_conditions.append(Product.id.in_(variant_prod_ids))

    productos = Product.query.options(joinedload(Product.variantes)).filter_by(
        tipo_inventario='tienda', activo=True
    ).filter(or_(*filter_conditions)).limit(80).all()
    
    results = []
    for p in productos:
        score = score_product_search(q_norm, p.nombre, p.sku, p.variantes)
        var_list = []
        for v in p.variantes:
            var_list.append({
                'id': v.id,
                'nombre': v.nombre_variante,
                'stock': v.cantidad_stock,
                'precio_sugerido': float(v.precio_sugerido or p.precio_sugerido)
            })
        results.append({
            'id': p.id,
            'nombre': p.nombre,
            'sku': p.sku,
            'stock': p.total_stock,
            'total_stock': p.total_stock,
            'precio_sugerido': float(p.precio_sugerido),
            'tiene_variantes': bool(p.variantes),
            'variantes': var_list,
            'es_sim': False,
            '_score': score
        })
        
    # Buscar SIMs disponibles complementariamente
    from models import SimCard
    sims = SimCard.query.filter_by(estado='Disponible').filter(
        or_(
            SimCard.numero_telefono.ilike(search_term),
            SimCard.iccid.ilike(search_term),
            SimCard.operador.ilike(search_term)
        )
    ).limit(30).all()
    
    for sim in sims:
        sim_nombre = f"[SIM {sim.operador.upper()}] {sim.numero_telefono}"
        sim_score = score_product_search(q_norm, sim_nombre, sim.iccid)
        tel_norm = normalize_search_str(sim.numero_telefono)
        if tel_norm.startswith(q_norm):
            sim_score = min(sim_score, 1)
        elif q_norm in tel_norm:
            sim_score = min(sim_score, 5)

        results.append({
            'id': sim.id,
            'nombre': sim_nombre,
            'sku': sim.iccid,
            'stock': 1,
            'total_stock': 1,
            'precio_sugerido': float(sim.precio_venta),
            'tiene_variantes': False,
            'variantes': [],
            'es_sim': True,
            '_score': sim_score
        })

    # Ordenar priorizando:
    # 1. _score (menor es mejor: 0 exacto, 1 inicio nombre, 2 inicio sku, 3 palabra, etc.)
    # 2. stock > 0 (los que tienen stock físico primero)
    # 3. stock total descendente
    # 4. nombre alfabético
    results.sort(key=lambda item: (
        item['_score'],
        0 if item['stock'] > 0 else 1,
        -item['stock'],
        normalize_search_str(item['nombre'])
    ))

    # Devolver los mejores 30 resultados sin el campo auxiliar _score
    clean_results = []
    for r in results[:30]:
        r.pop('_score', None)
        clean_results.append(r)

    return jsonify(clean_results)

# Ruta para la Impresión del formato Térmico (Ticket)
@sales_bp.route('/recibo/<int:sale_id>', methods=['GET'])
@login_required # Proteger confidencialidad del cajero
def imprimir_ticket(sale_id):
    # Regla: Retorna 404 si alguien ingresa un ID falso
    venta = Sale.query.get_or_404(sale_id)
    return render_template('sales/ticket.html', venta=venta)

# Endpoint Historial de Ventas / Ventas del Día
@sales_bp.route('/historial', methods=['GET'])
@login_required
def historial():
    if current_user.rol not in ['admin', 'vendedor']:
        abort(403)

    # Calcular el valor exacto de 'HOY' en Bogotá
    hoy_bogota = obtener_hora_bogota().strftime('%Y-%m-%d')
    
    # Si el usuario es vendedor: acceso estrictamente limitado a las ventas del DÍA ACTUAL
    if current_user.rol == 'vendedor':
        fecha_inicio = hoy_bogota
        fecha_fin = hoy_bogota
    else:
        # Administrador: permite consultar cualquier rango de fechas o colapsa a HOY por defecto
        fecha_inicio = request.args.get('fecha_inicio', hoy_bogota)
        fecha_fin = request.args.get('fecha_fin', hoy_bogota)
    
    # Optimización: eager loading (evita N+1 con joinedload)
    query = Sale.query.options(joinedload(Sale.vendedor))
    
    # Motor de búsqueda por Rango Restricto con validación segura
    if fecha_inicio:
        try:
            inicio_dt = datetime.strptime(fecha_inicio, '%Y-%m-%d')
            query = query.filter(Sale.fecha_venta >= inicio_dt)
        except ValueError:
            pass
        
    if fecha_fin:
        try:
            fin_dt = datetime.strptime(fecha_fin, '%Y-%m-%d')
            # Sumar 1 día matemáticamente para incluir los registros hasta las 23:59:59 del último día
            query = query.filter(Sale.fecha_venta < fin_dt + timedelta(days=1))
        except ValueError:
            pass
        
    ventas = query.order_by(Sale.fecha_venta.desc()).all()
    
    # Auditar y cruzar sumatorios de métricas de pago
    # Sistema híbrido: usa SalePayment si existe, caso contrario cae al metodo_pago legacy
    total_efectivo = Decimal('0')
    total_nequi = Decimal('0')
    total_bancolombia = Decimal('0')
    total_daviplata = Decimal('0')
    total_tarjeta = Decimal('0')
    total_transferencia_legacy = Decimal('0')
    total_mixto = 0  # Contador de ventas con pago mixto

    for v in ventas:
        if v.pagos:  # Pagos nuevos con tabla sale_payments
            for pago in v.pagos:
                if pago.metodo_pago == 'efectivo':
                    total_efectivo += pago.monto
                elif pago.metodo_pago == 'nequi':
                    total_nequi += pago.monto
                elif pago.metodo_pago == 'bancolombia':
                    total_bancolombia += pago.monto
                elif pago.metodo_pago == 'daviplata':
                    total_daviplata += pago.monto
                elif pago.metodo_pago == 'tarjeta':
                    total_tarjeta += pago.monto
                elif pago.metodo_pago == 'transferencia':
                    total_transferencia_legacy += pago.monto
            if len(v.pagos) > 1:
                total_mixto += 1
        else:  # Retrocompatibilidad con ventas antiguas sin SalePayment
            if v.metodo_pago == 'efectivo':
                total_efectivo += v.monto_total
            elif v.metodo_pago == 'nequi':
                total_nequi += v.monto_total
            elif v.metodo_pago == 'bancolombia':
                total_bancolombia += v.monto_total
            elif v.metodo_pago == 'daviplata':
                total_daviplata += v.monto_total
            elif v.metodo_pago == 'tarjeta':
                total_tarjeta += v.monto_total
            elif v.metodo_pago == 'transferencia':
                total_transferencia_legacy += v.monto_total

    # Cálculos globales para dashboard financiero
    total_consolidado = sum((v.monto_total for v in ventas), Decimal('0'))
    total_operaciones = len(ventas)
    ticket_promedio = (total_consolidado / total_operaciones) if total_operaciones > 0 else Decimal('0')
    total_transferencias = total_nequi + total_bancolombia + total_daviplata + total_tarjeta + total_transferencia_legacy

    # Porcentajes de canales de pago
    pct_efectivo = round((float(total_efectivo) / float(total_consolidado) * 100), 1) if total_consolidado > 0 else 0
    pct_transferencias = round((float(total_transferencias) / float(total_consolidado) * 100), 1) if total_consolidado > 0 else 0

    pct_nequi = round((float(total_nequi) / float(total_transferencias) * 100), 1) if total_transferencias > 0 else 0
    pct_bancolombia = round((float(total_bancolombia) / float(total_transferencias) * 100), 1) if total_transferencias > 0 else 0
    pct_daviplata = round((float(total_daviplata) / float(total_transferencias) * 100), 1) if total_transferencias > 0 else 0
    pct_tarjeta = round((float(total_tarjeta) / float(total_transferencias) * 100), 1) if total_transferencias > 0 else 0

    # Envío al Engine de HTML
    return render_template('sales/historial.html', 
                           ventas=ventas, 
                           total_consolidado=total_consolidado,
                           total_operaciones=total_operaciones,
                           ticket_promedio=ticket_promedio,
                           total_efectivo=total_efectivo,
                           total_transferencias=total_transferencias,
                           pct_efectivo=pct_efectivo,
                           pct_transferencias=pct_transferencias,
                           total_nequi=total_nequi,
                           total_bancolombia=total_bancolombia,
                           total_daviplata=total_daviplata,
                           total_tarjeta=total_tarjeta,
                           total_transferencia_legacy=total_transferencia_legacy,
                           pct_nequi=pct_nequi,
                           pct_bancolombia=pct_bancolombia,
                           pct_daviplata=pct_daviplata,
                           pct_tarjeta=pct_tarjeta,
                           total_mixto=total_mixto,
                           fecha_inicio=fecha_inicio,
                           fecha_fin=fecha_fin)


# Endpoint para Anular/Eliminar Venta Histórica
@sales_bp.route('/eliminar/<int:sale_id>', methods=['POST'])
@login_required
@admin_required
def eliminar_venta(sale_id):
    venta = Sale.query.get_or_404(sale_id)
    
    try:
        # Revertir Stock de productos estándar
        for detalle in venta.detalles:
            if detalle.variant_id:
                variante = ProductVariant.query.with_for_update().get(detalle.variant_id)
                if variante:
                    variante.cantidad_stock += detalle.cantidad_vendida
            else:
                producto = Product.query.with_for_update().get(detalle.product_id)
                if producto:
                    producto.cantidad_stock += detalle.cantidad_vendida
                    
        # Revertir estado de SIMs asociadas a la transacción
        from models import SimCard
        sims_asociadas = SimCard.query.filter_by(sale_id=sale_id).all()
        for sim in sims_asociadas:
            sim.estado = 'Disponible'
            sim.vendedor_id = None
            sim.metodo_pago = None
            sim.precio_venta_real = None
            sim.fecha_venta = None
            sim.sale_id = None

        # Eliminar Venta y Detalles (Cascada)
        db.session.delete(venta)
        db.session.commit()
        flash('Venta anulada y stock devuelto exitosamente.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash('Ocurrió un error al anular la venta.', 'danger')
        
    return redirect(url_for('sales_bp.historial'))

# Endpoint para Modificar Método de Pago de una Venta (Soporta Único y Dividido)
@sales_bp.route('/cambiar-metodo-pago/<int:sale_id>', methods=['POST'])
@login_required
@admin_required
def cambiar_metodo_pago(sale_id):
    venta = Sale.query.get_or_404(sale_id)
    tipo_pago = request.form.get('tipo_pago', 'unico').strip().lower()
    
    # Preservar filtros de fecha activos
    fecha_inicio = request.form.get('fecha_inicio', '').strip()
    fecha_fin = request.form.get('fecha_fin', '').strip()
    params = {}
    if fecha_inicio:
        params['fecha_inicio'] = fecha_inicio
    if fecha_fin:
        params['fecha_fin'] = fecha_fin

    try:
        if tipo_pago == 'dividido':
            # Leer montos divididos
            montos = {
                'efectivo': Decimal(request.form.get('monto_efectivo', '0') or '0'),
                'nequi': Decimal(request.form.get('monto_nequi', '0') or '0'),
                'bancolombia': Decimal(request.form.get('monto_bancolombia', '0') or '0'),
                'daviplata': Decimal(request.form.get('monto_daviplata', '0') or '0'),
                'tarjeta': Decimal(request.form.get('monto_tarjeta', '0') or '0')
            }
            
            # Filtrar solo montos mayores a 0
            pagos_activos = {k: v for k, v in montos.items() if v > 0}
            
            if not pagos_activos:
                flash('Debes ingresar al menos un monto mayor a cero para el pago dividido.', 'warning')
                return redirect(url_for('sales_bp.historial', **params))
                
            total_ingresado = sum(pagos_activos.values())
            
            # Validar que la suma coincida con el total de la venta (tolerancia de 1 peso por redondeo)
            if abs(total_ingresado - venta.monto_total) > Decimal('1'):
                flash(f'La suma de los métodos divididos (${total_ingresado:,.0f}) no coincide con el total del ticket (${venta.monto_total:,.0f}).', 'danger')
                return redirect(url_for('sales_bp.historial', **params))
                
            # Limpiar pagos previos
            SalePayment.query.filter_by(sale_id=venta.id).delete()
            
            # Insertar nuevos pagos en sale_payments
            for metodo, monto in pagos_activos.items():
                pago = SalePayment(
                    sale_id=venta.id,
                    metodo_pago=metodo,
                    monto=monto
                )
                db.session.add(pago)
                
            # Asignar método principal
            if len(pagos_activos) > 1:
                venta.metodo_pago = 'mixto'
                metodo_sims = 'mixto'
            else:
                unico_metodo = list(pagos_activos.keys())[0]
                venta.metodo_pago = unico_metodo
                metodo_sims = unico_metodo
                
            # Sincronizar SIMs si existiesen
            from models import SimCard
            sims_asociadas = SimCard.query.filter_by(sale_id=sale_id).all()
            for sim in sims_asociadas:
                sim.metodo_pago = metodo_sims
                
            db.session.commit()
            flash(f'Vía de pago del Ticket #{venta.id:05d} actualizada exitosamente a Pago Dividido.', 'success')

        else:
            # Modo Método Único
            nuevo_metodo = request.form.get('nuevo_metodo', '').strip().lower()
            metodos_validos = ['efectivo', 'nequi', 'bancolombia', 'daviplata', 'tarjeta']
            if nuevo_metodo not in metodos_validos:
                flash('Método de pago no válido.', 'danger')
                return redirect(url_for('sales_bp.historial', **params))
                
            venta.metodo_pago = nuevo_metodo
            SalePayment.query.filter_by(sale_id=venta.id).delete()
            nuevo_pago = SalePayment(
                sale_id=venta.id,
                metodo_pago=nuevo_metodo,
                monto=venta.monto_total
            )
            db.session.add(nuevo_pago)
            
            from models import SimCard
            sims_asociadas = SimCard.query.filter_by(sale_id=sale_id).all()
            for sim in sims_asociadas:
                sim.metodo_pago = nuevo_metodo
                
            db.session.commit()
            
            nombres = {
                'efectivo': 'Efectivo',
                'nequi': 'Nequi',
                'bancolombia': 'Bancolombia',
                'daviplata': 'Daviplata',
                'tarjeta': 'Bolt (Datáfono)'
            }
            flash(f'Método de pago del Ticket #{venta.id:05d} actualizado a {nombres.get(nuevo_metodo, nuevo_metodo)}.', 'success')
            
    except Exception as e:
        db.session.rollback()
        flash(f'Ocurrió un error al actualizar el pago: {str(e)}', 'danger')
        
    return redirect(url_for('sales_bp.historial', **params))

# Endpoint Catálogo Estricto de solo vista para Operarios
@sales_bp.route('/catalogo', methods=['GET'])
@login_required 
def catalogo():
    query_str = request.args.get('q', '').strip()
    
    if query_str:
        q_norm = normalize_search_str(query_str)
        search_term = f"%{query_str}%"
        
        # Buscar también coincidencias en subcategorías / variantes
        var_matches = ProductVariant.query.filter(
            ProductVariant.nombre_variante.ilike(search_term)
        ).limit(60).all()
        variant_prod_ids = [v.product_id for v in var_matches]

        filter_conditions = [
            Product.sku.ilike(search_term), 
            Product.nombre.ilike(search_term)
        ]
        if variant_prod_ids:
            filter_conditions.append(Product.id.in_(variant_prod_ids))

        productos = Product.query.options(joinedload(Product.variantes)).filter_by(
            tipo_inventario='tienda', activo=True
        ).filter(or_(*filter_conditions)).limit(100).all()

        # Priorizar iniciales y stock disponible
        productos.sort(key=lambda p: (
            score_product_search(q_norm, p.nombre, p.sku, p.variantes),
            0 if p.total_stock > 0 else 1,
            -p.total_stock,
            normalize_search_str(p.nombre)
        ))
        productos = productos[:60]
    else:
        # Límite pasivo de 50 ítems para ahorrar memoria RAM de BD en carga inicial
        productos = Product.query.filter_by(tipo_inventario='tienda', activo=True).limit(50).all()
        
    return render_template('sales/catalogo.html', productos=productos, q=query_str)


# ─── SISTEMA DE APROBACIÓN REMOTA DE PRECIOS ────────────────────────────────

@sales_bp.route('/api/precio/solicitar', methods=['POST'])
@login_required
def api_solicitar_precio():
    """
    El vendedor crea una solicitud de precio especial desde el POS.
    Body JSON: { product_id, variant_id (opt), precio_solicitado, precio_original }
    Retorna:   { solicitud_id }
    """
    from models import PriceApproval
    data = request.get_json(silent=True) or {}

    product_id        = data.get('product_id')
    variant_id        = data.get('variant_id')
    precio_solicitado = data.get('precio_solicitado')
    precio_original   = data.get('precio_original')

    if not all([product_id, precio_solicitado is not None, precio_original is not None]):
        return jsonify({'error': 'Datos incompletos en la solicitud.'}), 400

    producto = Product.query.get(product_id)
    if not producto:
        return jsonify({'error': 'Producto no encontrado.'}), 404

    # Cancelar solicitudes previas pendientes del mismo vendedor+producto (evita duplicados)
    PriceApproval.query.filter_by(
        vendedor_id=current_user.id,
        product_id=product_id,
        variant_id=variant_id,
        estado='pendiente'
    ).update({'estado': 'cancelada'})

    solicitud = PriceApproval(
        vendedor_id=current_user.id,
        product_id=product_id,
        variant_id=variant_id if variant_id else None,
        precio_original=Decimal(str(precio_original)),
        precio_solicitado=Decimal(str(precio_solicitado))
    )
    try:
        db.session.add(solicitud)
        db.session.commit()
        return jsonify({'solicitud_id': solicitud.id}), 201
    except Exception:
        db.session.rollback()
        return jsonify({'error': 'Error al guardar la solicitud.'}), 500


@sales_bp.route('/api/precio/estado/<int:solicitud_id>', methods=['GET'])
@login_required
def api_estado_solicitud(solicitud_id):
    """
    Endpoint de polling: el POS consulta cada 3 s si la solicitud fue resuelta.
    Solo el propio vendedor (o admin) puede consultar su solicitud.
    Retorna: { estado, precio_aprobado, motivo_rechazo }
    """
    from models import PriceApproval
    solicitud = PriceApproval.query.get_or_404(solicitud_id)

    if solicitud.vendedor_id != current_user.id and current_user.rol != 'admin':
        return jsonify({'error': 'Acceso denegado.'}), 403

    return jsonify({
        'estado':           solicitud.estado,
        'precio_aprobado':  float(solicitud.precio_aprobado) if solicitud.precio_aprobado else None,
        'motivo_rechazo':   solicitud.motivo_rechazo
    })
