# pyright: reportCallIssue=false
from flask import Blueprint, render_template, abort, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from models import db, Product, ProductVariant, Sale, User, SaleDetail, SalePayment, StockAdjustment, Expense, Loss, Provider, ProviderInvoice, ProviderPayment, Warranty, DynamicKey, obtener_hora_bogota, SimCard
from sqlalchemy.sql import func
from werkzeug.security import generate_password_hash
from decorators import admin_required
import string, random
from datetime import timedelta

admin_bp = Blueprint('admin_bp', __name__)

@admin_bp.route('/generar-clave', methods=['POST'])
@login_required
@admin_required
def generar_clave():
    # Generar un código alfanumérico random de 6 caracteres
    codigo = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    
    # Expiración: 10 minutos
    ahora = obtener_hora_bogota()
    expira = ahora + timedelta(minutes=10)
    
    nueva_clave = DynamicKey(
        key_code=codigo,
        admin_id=current_user.id,
        created_at=ahora,
        expires_at=expira
    )
    db.session.add(nueva_clave)
    db.session.commit()
    
    return jsonify({'success': True, 'codigo': codigo})

@admin_bp.route('/vendedores', methods=['GET', 'POST'])
@login_required
@admin_required
def vendedores():
    if request.method == 'POST':
        nombre = request.form.get('nombre')
        email = request.form.get('email')
        telefono = request.form.get('telefono')
        password = request.form.get('password')
        
        # Se previene registrar vendedores con un mismo email para preservar la unicidad de las credenciales de acceso
        if User.query.filter_by(email=email).first():
            flash('Acción Denegada: Ese correo ya le pertenece a otro vendedor.', 'danger')
        else:
            try:
                # Se aplica un hash a la contraseña para evitar guardar texto plano, previniendo exposición en caso de brechas
                nuevo_vendedor = User(
                    nombre=nombre.strip(),
                    email=email.strip(),
                    telefono=telefono.strip() if telefono else None,
                    password_hash=generate_password_hash(password),
                    rol='vendedor'
                )
                db.session.add(nuevo_vendedor)
                db.session.commit()
                flash(f"¡Vendedor '{nombre}' registrado y autorizado para Cajas!", "success")
            except Exception as e:
                db.session.rollback()
                flash('Ocurrió un error en la base de datos al intentar registrar al vendedor.', 'danger')
            
        return redirect(url_for('admin_bp.vendedores'))
        
    # Se pasa la lista para poblar la tabla HTML de gestión de personal
    lista_vendedores = User.query.filter_by(rol='vendedor').order_by(User.nombre).all()
    return render_template('admin/vendedores.html', vendedores=lista_vendedores)

@admin_bp.route('/vendedores/editar/<int:id>', methods=['POST'])
@login_required
@admin_required
def editar_vendedor(id):
    vendedor = User.query.get_or_404(id)
    nombre = request.form.get('nombre')
    email = request.form.get('email')
    telefono = request.form.get('telefono')
    password = request.form.get('password')
    
    # Validar email único si cambió
    if email != vendedor.email:
        if User.query.filter_by(email=email).first():
            flash('Error: El nuevo correo ya está en uso por otro usuario.', 'danger')
            return redirect(url_for('admin_bp.vendedores'))

    vendedor.nombre = nombre.strip()
    vendedor.email = email.strip()
    vendedor.telefono = telefono.strip() if telefono else None
    
    if password and password.strip():
        vendedor.password_hash = generate_password_hash(password)
        
    try:
        db.session.commit()
        flash(f'Vendedor "{nombre}" actualizado correctamente.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error al actualizar el vendedor.', 'danger')
        
    return redirect(url_for('admin_bp.vendedores'))

@admin_bp.route('/vendedores/eliminar/<int:id>', methods=['POST'])
@login_required
@admin_required
def eliminar_vendedor(id):
    vendedor = User.query.get_or_404(id)
    nombre = vendedor.nombre
    
    # No permitir que un admin borre a otro admin desde aquí o a sí mismo
    if vendedor.rol == 'admin':
        flash('No se pueden eliminar cuentas de administrador desde este panel.', 'danger')
        return redirect(url_for('admin_bp.vendedores'))

    try:
        db.session.delete(vendedor)
        db.session.commit()
        flash(f'Vendedor "{nombre}" eliminado con éxito.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error: No se pudo eliminar el vendedor (puede tener ventas u operaciones registradas).', 'danger')
        
    return redirect(url_for('admin_bp.vendedores'))

@admin_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    from datetime import datetime
    from models import (
        Product, ProductVariant, Sale, User, SaleDetail, SalePayment,
        StockAdjustment, Expense, Loss, Provider, ProviderInvoice, ProviderPayment,
        Warranty, SimCard, PriceApproval, obtener_hora_bogota
    )

    hoy = obtener_hora_bogota()
    
    # Parámetros de filtro de fecha:
    # Acepta 'mes' (YYYY-MM) o select_mes (1..12) y select_anio (YYYY)
    mes_str = request.args.get('mes')
    select_mes = request.args.get('select_mes')
    select_anio = request.args.get('select_anio')

    if select_mes and select_anio:
        try:
            m = int(select_mes)
            y = int(select_anio)
            inicio_mes = datetime(y, m, 1)
        except (ValueError, TypeError):
            inicio_mes = hoy.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif mes_str:
        try:
            inicio_mes = datetime.strptime(mes_str, '%Y-%m')
        except ValueError:
            inicio_mes = hoy.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        inicio_mes = hoy.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
    # Calcular el primer día del siguiente mes para delimitar la consulta
    if inicio_mes.month == 12:
        fin_mes = datetime(inicio_mes.year + 1, 1, 1)
    else:
        fin_mes = datetime(inicio_mes.year, inicio_mes.month + 1, 1)
        
    mes_seleccionado = inicio_mes.strftime('%Y-%m')
    anio_seleccionado = inicio_mes.year
    mes_num_seleccionado = inicio_mes.month
    
    # Mapeo de meses en español
    meses_es = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
    nombre_mes = meses_es[inicio_mes.month - 1]

    # --- CARD 1: INGRESOS (MES) ---
    ventas_query = Sale.query.filter(Sale.fecha_venta >= inicio_mes, Sale.fecha_venta < fin_mes).all()
    total_ventas = sum(float(v.monto_total or 0.0) for v in ventas_query)
    ventas_realizadas_count = len(ventas_query)

    # Desglose de ingresos (Efectivo/Transferencia vs Tarjeta)
    ingresos_tarjeta = 0.0
    ingresos_efectivo_transferencia = 0.0

    for v in ventas_query:
        if v.pagos:
            for p in v.pagos:
                monto_pago = float(p.monto or 0.0)
                if p.metodo_pago == 'tarjeta':
                    ingresos_tarjeta += monto_pago
                else:
                    ingresos_efectivo_transferencia += monto_pago
        else:
            monto_v = float(v.monto_total or 0.0)
            if v.metodo_pago == 'tarjeta':
                ingresos_tarjeta += monto_v
            else:
                ingresos_efectivo_transferencia += monto_v

    # --- CARD 2: MERCANCÍA VENDIDA ---
    total_unidades_vendidas = db.session.query(func.sum(SaleDetail.cantidad_vendida)).join(Sale, SaleDetail.sale_id == Sale.id).filter(
        Sale.fecha_venta >= inicio_mes, Sale.fecha_venta < fin_mes
    ).scalar() or 0
    total_unidades_vendidas = int(total_unidades_vendidas)

    referencias_vendidas = db.session.query(func.count(func.distinct(SaleDetail.product_id))).join(Sale, SaleDetail.sale_id == Sale.id).filter(
        Sale.fecha_venta >= inicio_mes, Sale.fecha_venta < fin_mes, SaleDetail.product_id.isnot(None)
    ).scalar() or 0

    total_referencias_catalogo = Product.query.count()

    # --- CARD 3: GASTOS (MES) ---
    gastos_query = Expense.query.filter(Expense.fecha_gasto >= inicio_mes, Expense.fecha_gasto < fin_mes).all()
    total_gastos_mes = sum(float(g.monto or 0.0) for g in gastos_query)
    gastos_registrados_count = len(gastos_query)
    gastos_diarios = sum(float(g.monto or 0.0) for g in gastos_query if 'diario' in (g.tipo_gasto or '').lower())
    gastos_indirectos = sum(float(g.monto or 0.0) for g in gastos_query if 'indirecto' in (g.tipo_gasto or '').lower())

    # --- CARD 4: UTILIDAD ESTIMADA ---
    # Costo Directo (COGS)
    detalles_vendidos = db.session.query(SaleDetail, Product).outerjoin(Product, SaleDetail.product_id == Product.id).join(Sale, SaleDetail.sale_id == Sale.id).filter(
        Sale.fecha_venta >= inicio_mes, Sale.fecha_venta < fin_mes
    ).all()

    costos_directos_cogs = sum(
        (detalle.SaleDetail.cantidad_vendida * (
            float(detalle.SaleDetail.precio_costo_manual) if detalle.SaleDetail.precio_costo_manual is not None
            else (float(detalle.Product.precio_costo) if detalle.Product and detalle.Product.precio_costo else 0.0)
        )) for detalle in detalles_vendidos
    )

    utilidad_estimada = float(total_ventas) - float(costos_directos_cogs) - float(total_gastos_mes)

    # --- CARD 5: ALERTAS DE STOCK ---
    productos = Product.query.all()
    productos_bajo_stock = sum(1 for p in productos if p.total_stock <= 10)
    ajustes_stock_periodo = StockAdjustment.query.filter(
        StockAdjustment.fecha_ajuste >= inicio_mes, StockAdjustment.fecha_ajuste < fin_mes
    ).count()

    # --- CARD 6: ABONOS A PROVEEDORES ---
    abonos_proveedores_mes = float(db.session.query(func.sum(ProviderPayment.monto_abonado)).filter(
        ProviderPayment.fecha_pago >= inicio_mes, ProviderPayment.fecha_pago < fin_mes
    ).scalar() or 0.0)
    abonos_proveedores_count = ProviderPayment.query.filter(
        ProviderPayment.fecha_pago >= inicio_mes, ProviderPayment.fecha_pago < fin_mes
    ).count()

    total_deuda_facturas = float(db.session.query(func.sum(ProviderInvoice.monto_total)).scalar() or 0.0)
    total_deuda_abonos = float(db.session.query(func.sum(ProviderPayment.monto_abonado)).scalar() or 0.0)
    deuda_proveedores = max(0.0, total_deuda_facturas - total_deuda_abonos)
    total_proveedores = Provider.query.count()

    # --- CARD 7: APROBACIONES DE PRECIOS ---
    aprobaciones_totales_mes = PriceApproval.query.filter(
        PriceApproval.fecha_solicitud >= inicio_mes, PriceApproval.fecha_solicitud < fin_mes
    ).count()
    aprobaciones_autorizadas_mes = PriceApproval.query.filter(
        PriceApproval.fecha_solicitud >= inicio_mes, PriceApproval.fecha_solicitud < fin_mes,
        PriceApproval.estado == 'aprobado'
    ).count()
    aprobaciones_vendidas_mes = PriceApproval.query.filter(
        PriceApproval.fecha_solicitud >= inicio_mes, PriceApproval.fecha_solicitud < fin_mes,
        PriceApproval.estado == 'aprobado',
        PriceApproval.fue_vendido == True
    ).count()
    aprobaciones_pendientes = PriceApproval.query.filter_by(estado='pendiente').count()

    # --- OTRAS MÉTRICAS OPERATIVAS ---
    perdidas_valor = float(db.session.query(func.sum(Loss.cost_at_loss * Loss.quantity)).filter(Loss.date >= inicio_mes, Loss.date < fin_mes).scalar() or 0.0)
    porcentaje_perdidas = round((perdidas_valor / total_ventas * 100), 2) if total_ventas > 0 else 0.0

    total_garantias_mes = Warranty.query.filter(Warranty.created_at >= inicio_mes, Warranty.created_at < fin_mes).count()
    garantias_pendientes = Warranty.query.filter(Warranty.resolution == 'Pendiente').count()

    sims_disponibles = SimCard.query.filter_by(estado='Disponible').count()
    sims_vendidas_mes = SimCard.query.filter(SimCard.estado == 'Vendida', SimCard.fecha_venta >= inicio_mes, SimCard.fecha_venta < fin_mes).count()

    return render_template('admin/dashboard.html',
                           nombre_mes=nombre_mes,
                           mes_seleccionado=mes_seleccionado,
                           anio_seleccionado=anio_seleccionado,
                           mes_num_seleccionado=mes_num_seleccionado,
                           total_ventas=total_ventas,
                           ventas_realizadas_count=ventas_realizadas_count,
                           ingresos_efectivo_transferencia=ingresos_efectivo_transferencia,
                           ingresos_tarjeta=ingresos_tarjeta,
                           total_unidades_vendidas=total_unidades_vendidas,
                           referencias_vendidas=referencias_vendidas,
                           total_referencias_catalogo=total_referencias_catalogo,
                           total_gastos_mes=total_gastos_mes,
                           gastos_registrados_count=gastos_registrados_count,
                           gastos_diarios=gastos_diarios,
                           gastos_indirectos=gastos_indirectos,
                           costos_directos_cogs=costos_directos_cogs,
                           utilidad_estimada=utilidad_estimada,
                           productos_bajo_stock=productos_bajo_stock,
                           ajustes_stock_periodo=ajustes_stock_periodo,
                           abonos_proveedores_mes=abonos_proveedores_mes,
                           abonos_proveedores_count=abonos_proveedores_count,
                           deuda_proveedores=deuda_proveedores,
                           total_proveedores=total_proveedores,
                           aprobaciones_totales_mes=aprobaciones_totales_mes,
                           aprobaciones_autorizadas_mes=aprobaciones_autorizadas_mes,
                           aprobaciones_vendidas_mes=aprobaciones_vendidas_mes,
                           aprobaciones_pendientes=aprobaciones_pendientes,
                           total_perdidas=perdidas_valor,
                           porcentaje_perdidas=porcentaje_perdidas,
                           total_garantias_mes=total_garantias_mes,
                           garantias_pendientes=garantias_pendientes,
                           sims_disponibles=sims_disponibles,
                           sims_vendidas_mes=sims_vendidas_mes)

# --- ENDPOINTS MODULO PERDIDAS ---
@admin_bp.route('/perdidas')
@login_required
@admin_required
def perdidas():
    ultimas_perdidas = Loss.query.order_by(Loss.date.desc()).all()
    return render_template('admin/perdidas.html', ultimas_perdidas=ultimas_perdidas)


@admin_bp.route('/aprobaciones/panel')
@login_required
@admin_required
def panel_aprobaciones():
    """Página dedicada para gestionar solicitudes en vivo y auditar el historial de aprobaciones que terminaron en venta."""
    from models import PriceApproval
    
    solicitudes_historial = PriceApproval.query.filter(
        PriceApproval.estado.in_(['aprobado', 'rechazado'])
    ).order_by(PriceApproval.fecha_resolucion.desc()).all()

    total_aprobadas = PriceApproval.query.filter_by(estado='aprobado').count()
    aprobadas_vendidas = PriceApproval.query.filter_by(estado='aprobado', fue_vendido=True).count()
    aprobadas_sin_vender = total_aprobadas - aprobadas_vendidas
    total_rechazadas = PriceApproval.query.filter_by(estado='rechazado').count()
    tasa_conversion = round((aprobadas_vendidas / total_aprobadas * 100), 1) if total_aprobadas > 0 else 0.0

    return render_template(
        'admin/aprobaciones.html',
        historial=solicitudes_historial,
        total_aprobadas=total_aprobadas,
        aprobadas_vendidas=aprobadas_vendidas,
        aprobadas_sin_vender=aprobadas_sin_vender,
        total_rechazadas=total_rechazadas,
        tasa_conversion=tasa_conversion
    )

@admin_bp.route('/api/product/<sku>')
@login_required
@admin_required
def api_producto_codigo(sku):
    producto = Product.query.filter_by(sku=sku.strip()).first()
    if not producto:
        return jsonify({'error': 'Producto no encontrado'}), 404
        
    return jsonify({
        'id': producto.id,
        'nombre': producto.nombre,
        'precio_costo': float(producto.precio_costo)
    })

@admin_bp.route('/perdidas/registrar', methods=['POST'])
@login_required
@admin_required
def registrar_perdida():
    product_id = request.form.get('product_id')
    cantidad = int(request.form.get('cantidad', 0))
    motivo = request.form.get('motivo', '').strip()
    
    if not product_id or cantidad <= 0:
        flash('Datos inválidos para registrar la pérdida.', 'danger')
        return redirect(url_for('admin_bp.dashboard'))
        
    producto = Product.query.get(product_id)
    if not producto:
        flash('El producto seleccionado no existe en el sistema.', 'danger')
        return redirect(url_for('admin_bp.dashboard'))
        
    if producto.cantidad_stock < cantidad:
        flash(f'Stock insuficiente. No puedes registrar una pérdida de {cantidad} si el sistema solo registra {producto.cantidad_stock} unidades.', 'danger')
        return redirect(url_for('admin_bp.dashboard'))
        
    try:
        # Descuento en stock central
        stock_anterior = producto.cantidad_stock
        producto.cantidad_stock -= cantidad
        
        costo_actual = producto.precio_costo
        
        # Registrar pérdida
        nueva_perdida = Loss(
            product_id=producto.id,
            user_id=current_user.id,
            quantity=cantidad,
            cost_at_loss=costo_actual,
            reason=motivo
        )
        db.session.add(nueva_perdida)
        
        # Rastreabilidad en Kardex
        ajuste = StockAdjustment(
            product_id=producto.id,
            admin_id=current_user.id,
            tipo_movimiento=f'Merma/Pérdida Registrada ({motivo})',
            stock_anterior=stock_anterior,
            stock_nuevo=producto.cantidad_stock
        )
        db.session.add(ajuste)
        
        db.session.commit()
        flash(f'Pérdida por {cantidad} unidades registrada con éxito. Inventario deducido.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('No se pudo registrar la pérdida por un error interno.', 'danger')
        
    return redirect(url_for('admin_bp.perdidas'))
# ---------------------------------


@admin_bp.route('/balance-financiero', methods=['GET', 'POST'])
@login_required
@admin_required
def balance_financiero():
    if request.method == 'POST':
        fecha_inicio_str = request.form.get('fecha_inicio')
        fecha_fin_str = request.form.get('fecha_fin')
    else:
        fecha_inicio_str = request.args.get('fecha_inicio')
        fecha_fin_str = request.args.get('fecha_fin')

    hoy = obtener_hora_bogota()
    import calendar
    if not fecha_inicio_str or not fecha_fin_str:
        # Por defecto, el mes actual
        primer_dia = hoy.replace(day=1)
        ultimo_dia_mes = calendar.monthrange(hoy.year, hoy.month)[1]
        ultimo_dia = hoy.replace(day=ultimo_dia_mes)
        
        fecha_inicio_str = primer_dia.strftime('%Y-%m-%d')
        fecha_fin_str = ultimo_dia.strftime('%Y-%m-%d')

    from datetime import datetime, timedelta
    try:
        inicio_dt = datetime.strptime(fecha_inicio_str, '%Y-%m-%d')
        fin_dt = datetime.strptime(fecha_fin_str, '%Y-%m-%d')
        # Avanzamos límite al inicio del siguiente día matemáticamente
        fin_dt_query = fin_dt + timedelta(days=1)
    except ValueError:
        flash("Formato de fecha inválido.", "danger")
        return redirect(url_for('admin_bp.dashboard'))

    # 1. Ventas Totales
    ventas_query = Sale.query.filter(Sale.fecha_venta >= inicio_dt, Sale.fecha_venta < fin_dt_query).all()
    
    ventas_efectivo = sum(v.monto_total for v in ventas_query if v.metodo_pago == 'efectivo')
    ventas_transferencia = sum(v.monto_total for v in ventas_query if v.metodo_pago in ['transferencia', 'nequi', 'bancolombia', 'daviplata', 'tarjeta'])
    total_ingresos = ventas_efectivo + ventas_transferencia

    # 2. Costo de Mercancía Vendida (COGS)
    detalles_vendidos = db.session.query(SaleDetail, Product).join(Product, SaleDetail.product_id == Product.id).join(Sale, SaleDetail.sale_id == Sale.id).filter(
        Sale.fecha_venta >= inicio_dt,
        Sale.fecha_venta < fin_dt_query
    ).all()
    
    costos_directos = sum((detalle.SaleDetail.cantidad_vendida * (detalle.Product.precio_costo or 0)) for detalle in detalles_vendidos)

    # 3. Costos Indirectos y Gastos Operativos
    gastos_query = Expense.query.filter(Expense.fecha_gasto >= inicio_dt, Expense.fecha_gasto < fin_dt_query).all()
    
    costos_indirectos = sum(g.monto for g in gastos_query if g.tipo_gasto == 'Costo Indirecto')
    gastos_operacionales = sum(g.monto for g in gastos_query if g.tipo_gasto == 'Gasto Diario')
    
    # 4. Mermas y Pérdidas
    perdidas_query = Loss.query.filter(Loss.date >= inicio_dt, Loss.date < fin_dt_query).all()
    costo_perdidas = sum((p.cost_at_loss * p.quantity) for p in perdidas_query)
    
    total_salidas = float(costos_directos) + float(costos_indirectos) + float(gastos_operacionales) + float(costo_perdidas)
    balance_neto = float(total_ingresos) - total_salidas

    datos_financieros = {
        'ventas_efectivo': float(ventas_efectivo),
        'ventas_transferencia': float(ventas_transferencia),
        'total_ingresos': float(total_ingresos),
        'costos_directos': float(costos_directos),
        'costos_indirectos': float(costos_indirectos),
        'gastos_operacionales': float(gastos_operacionales),
        'costo_perdidas': float(costo_perdidas),
        'total_salidas': total_salidas,
        'balance_neto': balance_neto
    }

    return render_template(
        'admin/balance_reporte.html',
        fecha_inicio=fecha_inicio_str,
        fecha_fin=fecha_fin_str,
        fecha_generacion=hoy.strftime('%Y-%m-%d %H:%M'),
        datos=datos_financieros
    )


# ─── SISTEMA DE APROBACIÓN REMOTA DE PRECIOS ────────────────────────────────

@admin_bp.route('/aprobaciones', methods=['GET'])
@login_required
@admin_required
def aprobaciones_precio():
    """
    API JSON: devuelve todas las solicitudes pendientes.
    El Dashboard las consulta cada 4 s para mostrar el widget de aprobaciones.
    """
    from models import PriceApproval
    solicitudes = PriceApproval.query.filter_by(estado='pendiente').order_by(
        PriceApproval.fecha_solicitud.asc()
    ).all()

    resultado = []
    for s in solicitudes:
        nombre_variante = s.variante.nombre_variante if s.variante else None
        resultado.append({
            'id':                s.id,
            'vendedor':          s.vendedor.nombre,
            'producto':          s.producto.nombre,
            'variante':          nombre_variante,
            'precio_original':   float(s.precio_original),
            'precio_solicitado': float(s.precio_solicitado),
            'hace':              _tiempo_relativo(s.fecha_solicitud)
        })
    return jsonify(resultado)


@admin_bp.route('/aprobaciones/<int:solicitud_id>/aprobar', methods=['POST'])
@login_required
@admin_required
def aprobar_precio(solicitud_id):
    """
    El admin aprueba la solicitud, opcionalmente con un precio diferente.
    Body JSON: { precio_aprobado (opcional) }
    """
    from models import PriceApproval
    solicitud = PriceApproval.query.get_or_404(solicitud_id)

    if solicitud.estado != 'pendiente':
        return jsonify({'error': 'Esta solicitud ya fue resuelta.'}), 400

    data = request.get_json(silent=True) or {}
    precio_final = data.get('precio_aprobado', float(solicitud.precio_solicitado))

    solicitud.estado           = 'aprobado'
    solicitud.precio_aprobado  = precio_final
    solicitud.admin_id         = current_user.id
    solicitud.fecha_resolucion = obtener_hora_bogota()

    try:
        db.session.commit()
        return jsonify({'ok': True, 'precio_aprobado': float(solicitud.precio_aprobado)})
    except Exception:
        db.session.rollback()
        return jsonify({'error': 'Error al guardar la aprobación.'}), 500


@admin_bp.route('/aprobaciones/<int:solicitud_id>/rechazar', methods=['POST'])
@login_required
@admin_required
def rechazar_precio(solicitud_id):
    """
    El admin rechaza la solicitud con un motivo opcional.
    Body JSON: { motivo (opcional) }
    """
    from models import PriceApproval
    solicitud = PriceApproval.query.get_or_404(solicitud_id)

    if solicitud.estado != 'pendiente':
        return jsonify({'error': 'Esta solicitud ya fue resuelta.'}), 400

    data = request.get_json(silent=True) or {}
    solicitud.estado           = 'rechazado'
    solicitud.motivo_rechazo   = data.get('motivo', 'Sin motivo especificado.')
    solicitud.admin_id         = current_user.id
    solicitud.fecha_resolucion = obtener_hora_bogota()

    try:
        db.session.commit()
        return jsonify({'ok': True})
    except Exception:
        db.session.rollback()
        return jsonify({'error': 'Error al guardar el rechazo.'}), 500


def _tiempo_relativo(dt):
    """Helper: '2 min atrás', 'hace 5 s', etc."""
    if not dt:
        return ''
    ahora = obtener_hora_bogota()
    diff  = int((ahora - dt).total_seconds())
    if diff < 60:
        return f'hace {diff} s'
    elif diff < 3600:
        return f'hace {diff // 60} min'
    else:
        return f'hace {diff // 3600} h'
