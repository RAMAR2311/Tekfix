import os
from werkzeug.utils import secure_filename
from flask import current_app, Blueprint, render_template, request, redirect, url_for, flash, abort, send_file, jsonify
from flask_login import login_required, current_user
from models import db, Product, StockAdjustment, ProductVariant
from decorators import admin_required, admin_or_bodega_required
import pandas as pd
from io import BytesIO

inventory_bp = Blueprint('inventory_bp', __name__)

@inventory_bp.route('/', methods=['GET'])
@login_required
@admin_or_bodega_required
def index():
    tipo = 'bodega' if current_user.rol == 'bodega' else 'tienda'
    productos = Product.query.filter_by(tipo_inventario=tipo).order_by(Product.nombre).all()
    return render_template('inventory/index.html', productos=productos)

@inventory_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
@admin_or_bodega_required
def nuevo():
    if request.method == 'POST':
        # --- Manejo de Imagen ---
        imagen_filename = None
        if 'imagen' in request.files:
            file = request.files['imagen']
            if file and file.filename != '':
                filename = secure_filename(file.filename)
                file.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
                imagen_filename = filename

        # La instanciación agrupa todos los parámetros del nuevo producto
        tipo = 'bodega' if current_user.rol == 'bodega' else 'tienda'
        nuevo_prod = Product(
            sku=request.form.get('sku').strip(),
            nombre=request.form.get('nombre').strip(),
            tipo_inventario=tipo,
            cantidad_stock=int(request.form.get('cantidad_stock', 0)),
            precio_costo=float(request.form.get('precio_costo', 0.0)),
            precio_minimo=float(request.form.get('precio_minimo', 0.0)),
            precio_sugerido=float(request.form.get('precio_sugerido', 0.0)),
            imagen=imagen_filename,
            observacion=request.form.get('observacion')
        )
        try:
            db.session.add(nuevo_prod)
            db.session.commit()
            
            # Crear ajuste inicial automáticamente en el Kardex
            ajuste_inicial = StockAdjustment(
                product_id=nuevo_prod.id,
                admin_id=current_user.id,
                tipo_movimiento='Creación Inicial',
                stock_anterior=0,
                stock_nuevo=nuevo_prod.cantidad_stock
            )
            db.session.add(ajuste_inicial)
            db.session.commit()

            flash('Producto creado exitosamente.', 'success')
            return redirect(url_for('inventory_bp.index'))
        except Exception as e:
            db.session.rollback()
            flash('Error al intentar guardar el producto en la base de datos.', 'danger')
            
    return render_template('inventory/form.html')

@inventory_bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_or_bodega_required
def editar_producto(id):
    # get_or_404 protege la ruta en caso de que se envíe un ID inexistente en la URL
    producto = Product.query.get_or_404(id)
    tipo = 'bodega' if current_user.rol == 'bodega' else 'tienda'
    if producto.tipo_inventario != tipo:
        abort(403)
    
    if request.method == 'POST':
        stock_anterior = producto.cantidad_stock
        cantidad_stock_nueva = int(request.form.get('cantidad_stock', 0))
        
        # Actualizar Imagen si se sube una nueva
        if 'imagen' in request.files:
            file = request.files['imagen']
            if file and file.filename != '':
                filename = secure_filename(file.filename)
                file.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
                producto.imagen = filename
                
        # Se actualizan directamente las propiedades del objeto SQLAlchemy trackeado
        producto.sku = request.form.get('sku').strip()
        producto.nombre = request.form.get('nombre').strip()
        producto.cantidad_stock = cantidad_stock_nueva
        producto.precio_costo = float(request.form.get('precio_costo', 0.0))
        producto.precio_minimo = float(request.form.get('precio_minimo', 0.0))
        producto.precio_sugerido = float(request.form.get('precio_sugerido', 0.0))
        producto.observacion = request.form.get('observacion')
        
        try:
            if stock_anterior != cantidad_stock_nueva:
                ajuste = StockAdjustment(
                    product_id=producto.id,
                    admin_id=current_user.id,
                    tipo_movimiento='Ajuste Manual',
                    stock_anterior=stock_anterior,
                    stock_nuevo=cantidad_stock_nueva
                )
                db.session.add(ajuste)
                
            db.session.commit()
            flash('Producto actualizado correctamente en base de datos.', 'success')
            return redirect(url_for('inventory_bp.index'))
        except Exception as e:
            db.session.rollback()
            flash('Error en la base de datos al actualizar el producto.', 'danger')

    # El objeto producto se pasa a Jinja para auto-poblar (pre-llenar) el formulario en modo edición
    return render_template('inventory/form.html', producto=producto)

@inventory_bp.route('/historial-ajustes')
@login_required
@admin_or_bodega_required
def historial_ajustes():
    tipo = 'bodega' if current_user.rol == 'bodega' else 'tienda'
    ajustes = StockAdjustment.query.join(Product).filter(Product.tipo_inventario == tipo).order_by(StockAdjustment.fecha_ajuste.desc()).all()
    return render_template('inventory/historial_ajustes.html', ajustes=ajustes)

@inventory_bp.route('/ver/<int:id>', methods=['GET'])
@login_required
@admin_or_bodega_required
def ver_producto(id):
    producto = Product.query.get_or_404(id)
    tipo = 'bodega' if current_user.rol == 'bodega' else 'tienda'
    if producto.tipo_inventario != tipo:
        abort(403)
    ajustes = StockAdjustment.query.filter_by(product_id=id).order_by(StockAdjustment.fecha_ajuste.desc()).all()
    return render_template('inventory/ver.html', producto=producto, ajustes=ajustes)

@inventory_bp.route('/producto/<int:id>/agregar_variante', methods=['POST'])
@login_required
@admin_or_bodega_required
def agregar_variante(id):
    producto = Product.query.get_or_404(id)
    nombre_variante = request.form.get('nombre_variante')
    cantidad_stock = int(request.form.get('cantidad_stock', 0))
    
    precio_costo_req = request.form.get('precio_costo')
    precio_minimo_req = request.form.get('precio_minimo')
    precio_sugerido_req = request.form.get('precio_sugerido')

    if not nombre_variante:
        flash('El nombre de la variante es obligatorio.', 'danger')
        return redirect(url_for('inventory_bp.index'))

    nueva_variante = ProductVariant(
        product_id=producto.id,
        nombre_variante=nombre_variante,
        cantidad_stock=cantidad_stock,
        precio_costo=float(precio_costo_req) if precio_costo_req else producto.precio_costo,
        precio_minimo=float(precio_minimo_req) if precio_minimo_req else producto.precio_minimo,
        precio_sugerido=float(precio_sugerido_req) if precio_sugerido_req else producto.precio_sugerido
    )
    try:
        db.session.add(nueva_variante)
        # Opcionalmente descontar o trackear en Kardex? La instrucción solo dice: "crea la ruta para añadir la subcategoría"
        db.session.commit()
        flash(f'Variante "{nombre_variante}" agregada con éxito.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error al agregar la variante.', 'danger')

    return redirect(url_for('inventory_bp.index'))

@inventory_bp.route('/variante/<int:id>/editar', methods=['POST'])
@login_required
@admin_or_bodega_required
def editar_variante(id):
    variante = ProductVariant.query.get_or_404(id)
    
    variante.nombre_variante = request.form.get('nombre_variante')
    variante.cantidad_stock = int(request.form.get('cantidad_stock', variante.cantidad_stock))
    
    precio_costo_req = request.form.get('precio_costo')
    precio_minimo_req = request.form.get('precio_minimo')
    precio_sugerido_req = request.form.get('precio_sugerido')
    
    if precio_costo_req: variante.precio_costo = float(precio_costo_req)
    if precio_minimo_req: variante.precio_minimo = float(precio_minimo_req)
    if precio_sugerido_req: variante.precio_sugerido = float(precio_sugerido_req)
    
    try:
        db.session.commit()
        flash('Variante editada con éxito.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error al editar la variante.', 'danger')
        
    return redirect(url_for('inventory_bp.index'))

@inventory_bp.route('/plantilla-importacion')
@login_required
@admin_or_bodega_required
def descargar_plantilla():
    # Crear un DataFrame de estructura requerida
    df = pd.DataFrame(columns=['sku', 'nombre', 'cantidad_stock', 'precio_costo', 'precio_minimo', 'precio_sugerido', 'observacion'])
    
    # Filas de ejemplo para guiar al usuario
    df.loc[0] = ['SKU-EXAMPLE-01', 'Audífonos Bluetooth Inalambricos', 50, 10.50, 14.00, 20.00, 'Color azul noche']
    df.loc[1] = ['SKU-EXAMPLE-02', 'Cargador Original Carga Rápida', 100, 5.00, 7.50, 12.00, '']
    
    output = BytesIO()
    df.to_excel(output, index=False, engine='openpyxl')
    output.seek(0)
    
    return send_file(output, download_name="plantilla_importacion.xlsx", as_attachment=True)

@inventory_bp.route('/importar', methods=['POST'])
@login_required
@admin_or_bodega_required
def importar_inventario():
    if 'archivo' not in request.files:
        flash('No se seleccionó ningún archivo.', 'danger')
        return redirect(url_for('inventory_bp.index'))
        
    archivo = request.files['archivo']
    if archivo.filename == '':
        flash('Ningún archivo seleccionado.', 'danger')
        return redirect(url_for('inventory_bp.index'))
        
    if not (archivo.filename.endswith('.xlsx') or archivo.filename.endswith('.csv')):
        flash('Formato no válido. Solo debes subir archivos .xlsx o .csv', 'warning')
        return redirect(url_for('inventory_bp.index'))
        
    try:
        # Lectura con pandas según la extensión
        if archivo.filename.endswith('.csv'):
            df = pd.read_csv(archivo)
        else:
            df = pd.read_excel(archivo)
            
        required_cols = ['sku', 'nombre', 'cantidad_stock', 'precio_costo', 'precio_minimo', 'precio_sugerido', 'observacion']
        
        # Limpieza de encabezados para evitar problemas por mayúsculas o espacios accidentales
        df.columns = [str(c).strip().lower() for c in df.columns]
        
        missing = [c for c in required_cols if c not in df.columns]
        if missing:
            flash(f"El archivo rechazado. Faltan las siguientes columnas: {', '.join(missing)}", 'danger')
            return redirect(url_for('inventory_bp.index'))
            
        tipo = 'bodega' if current_user.rol == 'bodega' else 'tienda'
        creados = 0
        actualizados = 0
        
        for idx, row in df.iterrows():
            sku_raw = str(row['sku']).strip()
            if not sku_raw or sku_raw.lower() == 'nan':
                continue
                
            # Limpiar cantidades para evitar errores NaN o Nulls
            cant = int(row['cantidad_stock']) if pd.notna(row['cantidad_stock']) else 0
            costo = float(row['precio_costo']) if pd.notna(row['precio_costo']) else 0.0
            minimo = float(row['precio_minimo']) if pd.notna(row['precio_minimo']) else 0.0
            sugerido = float(row['precio_sugerido']) if pd.notna(row['precio_sugerido']) else 0.0
            nombre_val = str(row['nombre']).strip()
            obs_val = str(row['observacion']).strip() if pd.notna(row['observacion']) else ''
            if obs_val.lower() == 'nan':
                obs_val = ''

            prod = Product.query.filter_by(sku=sku_raw, tipo_inventario=tipo).first()
            
            if prod:
                # Si EXISTE, sumamos la cantidad como especificó y actualizamos los precios.
                stock_anterior = prod.cantidad_stock
                prod.cantidad_stock += cant
                prod.precio_costo = costo
                prod.precio_minimo = minimo
                prod.precio_sugerido = sugerido
                # Se podría o no actualizar el nombre, pero la instrucción dice "actualiza los precios"
                prod.nombre = nombre_val 
                prod.observacion = obs_val
                
                if cant > 0:
                    ajuste = StockAdjustment(
                        product_id=prod.id,
                        admin_id=current_user.id,
                        tipo_movimiento='Suma por Ingreso Masivo (Excel)',
                        stock_anterior=stock_anterior,
                        stock_nuevo=prod.cantidad_stock
                    )
                    db.session.add(ajuste)
                actualizados += 1
            else:
                # CREAR NUEVO
                nuevo_prod = Product(
                    sku=sku_raw,
                    nombre=nombre_val,
                    tipo_inventario=tipo,
                    cantidad_stock=cant,
                    precio_costo=costo,
                    precio_minimo=minimo,
                    precio_sugerido=sugerido,
                    observacion=obs_val
                )
                db.session.add(nuevo_prod)
                db.session.flush() # Generar ID autoincremental
                
                ajuste = StockAdjustment(
                    product_id=nuevo_prod.id,
                    admin_id=current_user.id,
                    tipo_movimiento='Creación Inicial (Excel)',
                    stock_anterior=0,
                    stock_nuevo=nuevo_prod.cantidad_stock
                )
                db.session.add(ajuste)
                creados += 1
                
        db.session.commit()
        flash(f'Carga masiva completada exitosamente. Productos creados: {creados} | Agregados a stock existente: {actualizados}.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Ocurrió un error leyendo las filas de tu archivo: {str(e)}', 'danger')
        
    return redirect(url_for('inventory_bp.index'))
