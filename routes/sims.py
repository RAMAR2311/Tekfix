from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from models import db, SimCard, obtener_hora_bogota
from decorators import admin_required
from sqlalchemy.sql import func
from datetime import datetime

sims_bp = Blueprint('sims_bp', __name__)

@sims_bp.route('/', methods=['GET'])
@login_required
def index():
    # --- Filtros de búsqueda ---
    search_query = request.args.get('search', '').strip()
    operador_filter = request.args.get('operador', '').strip()
    
    # Consulta base para Disponibles y Dañadas (Inventario Activo)
    query_dispo = SimCard.query.filter(SimCard.estado != 'Vendida')
    # Consulta base para Vendidas (Historial de Ventas)
    query_ventas = SimCard.query.filter_by(estado='Vendida')

    if search_query:
        search_filter = (
            (SimCard.numero_telefono.like(f"%{search_query}%")) | 
            (SimCard.iccid.like(f"%{search_query}%")) |
            (SimCard.observacion.like(f"%{search_query}%"))
        )
        query_dispo = query_dispo.filter(search_filter)
        query_ventas = query_ventas.filter(search_filter)

    if operador_filter:
        query_dispo = query_dispo.filter_by(operador=operador_filter)
        query_ventas = query_ventas.filter_by(operador=operador_filter)

    # Ordenar y obtener listas
    sims_disponibles_list = query_dispo.order_by(SimCard.fecha_registro.desc()).all()
    sims_vendidas_list = query_ventas.order_by(SimCard.fecha_venta.desc()).all()

    # --- KPIs y Métricas del Inventario de SIMs ---
    total_disponibles = SimCard.query.filter_by(estado='Disponible').count()
    total_vendidas = SimCard.query.filter_by(estado='Vendida').count()
    total_danadas = SimCard.query.filter_by(estado='Dañada').count()
    total_sims = SimCard.query.count()

    # Desglose por operadores para las tarjetas métricas
    claro_count = SimCard.query.filter_by(operador='Claro', estado='Disponible').count()
    movistar_count = SimCard.query.filter_by(operador='Movistar', estado='Disponible').count()
    tigo_count = SimCard.query.filter_by(operador='Tigo', estado='Disponible').count()
    wom_count = SimCard.query.filter_by(operador='Wom', estado='Disponible').count()

    # Recaudación total de SIMs (Independiente)
    total_recaudado = db.session.query(func.sum(SimCard.precio_venta_real)).filter_by(estado='Vendida').scalar() or 0.0

    return render_template(
        'sims/index.html',
        sims_disponibles_list=sims_disponibles_list,
        sims_vendidas_list=sims_vendidas_list,
        search_query=search_query,
        operador_filter=operador_filter,
        total_disponibles=total_disponibles,
        total_vendidas=total_vendidas,
        total_danadas=total_danadas,
        total_sims=total_sims,
        claro_count=claro_count,
        movistar_count=movistar_count,
        tigo_count=tigo_count,
        wom_count=wom_count,
        total_recaudado=total_recaudado
    )

@sims_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo():
    if request.method == 'POST':
        numero_telefono = request.form.get('numero_telefono', '').strip()
        iccid = request.form.get('iccid', '').strip()
        operador = request.form.get('operador', '').strip()
        precio_costo = float(request.form.get('precio_costo', 0.0) or 0.0)
        precio_venta = float(request.form.get('precio_venta', 0.0) or 0.0)
        observacion = request.form.get('observacion', '').strip()

        if not numero_telefono or not iccid or not operador:
            flash('Error: El número de teléfono, ICCID y operador son obligatorios.', 'danger')
            return redirect(url_for('sims_bp.nuevo'))

        # Validar ICCID único
        if SimCard.query.filter_by(iccid=iccid).first():
            flash(f'Error: Ya existe una SIM registrada con el ICCID/Serial "{iccid}".', 'danger')
            return redirect(url_for('sims_bp.nuevo'))

        try:
            nueva_sim = SimCard(
                numero_telefono=numero_telefono,
                iccid=iccid,
                operador=operador,
                precio_costo=precio_costo,
                precio_venta=precio_venta,
                estado='Disponible',
                observacion=observacion
            )
            db.session.add(nueva_sim)
            db.session.commit()
            flash(f'SIM con línea {numero_telefono} registrada correctamente.', 'success')
            return redirect(url_for('sims_bp.index'))
        except Exception as e:
            db.session.rollback()
            flash('Error al guardar la SIM en la base de datos.', 'danger')
            return redirect(url_for('sims_bp.nuevo'))

    return render_template('sims/form.html')

@sims_bp.route('/registrar-lote', methods=['POST'])
@login_required
def registrar_lote():
    operador = request.form.get('operador_lote', '').strip()
    precio_costo = float(request.form.get('precio_costo_lote', 0.0) or 0.0)
    precio_venta = float(request.form.get('precio_venta_lote', 0.0) or 0.0)
    lote_texto = request.form.get('lote_texto', '').strip()

    if not operador or not lote_texto:
        flash('Error: El operador y la lista de SIMs son obligatorios.', 'danger')
        return redirect(url_for('sims_bp.nuevo'))

    lineas = lote_texto.split('\n')
    creados = 0
    errores = 0

    for idx, linea in enumerate(lineas):
        linea = linea.strip()
        if not linea:
            continue
        
        parts = linea.split(',')
        if len(parts) >= 2:
            num = parts[0].strip()
            icc = parts[1].strip()
        elif len(parts) == 1:
            val = parts[0].strip()
            if len(val) == 10 and val.isdigit(): # Es número telefónico
                num = val
                icc = "GEN-" + val + datetime.now().strftime("%f")[:4]
            else: # Asumir ICCID/Serial
                num = "3000000000"
                icc = val
        else:
            errores += 1
            continue

        # Verificar unicidad de ICCID en lote
        if SimCard.query.filter_by(iccid=icc).first():
            errores += 1
            continue

        try:
            nueva_sim = SimCard(
                numero_telefono=num,
                iccid=icc,
                operador=operador,
                precio_costo=precio_costo,
                precio_venta=precio_venta,
                estado='Disponible'
            )
            db.session.add(nueva_sim)
            creados += 1
        except Exception:
            errores += 1
            continue

    try:
        db.session.commit()
        if creados > 0:
            flash(f'Carga masiva completada: {creados} SIMs creadas con éxito.' + (f' ({errores} errores/duplicados omitidos).' if errores > 0 else ''), 'success')
        else:
            flash(f'No se inyectó ningún registro. Se omitieron {errores} filas por errores o duplicados.', 'warning')
    except Exception:
        db.session.rollback()
        flash('Error grave al guardar el lote en la base de datos.', 'danger')

    return redirect(url_for('sims_bp.index'))

@sims_bp.route('/vender/<int:sim_id>', methods=['POST'])
@login_required
def vender(sim_id):
    sim = SimCard.query.get_or_404(sim_id)
    
    if sim.estado == 'Vendida':
        return jsonify({'success': False, 'error': 'Esta SIM ya fue vendida previamente.'}), 400

    precio_venta_real = float(request.form.get('precio_venta_real', sim.precio_venta) or 0.0)
    metodo_pago = request.form.get('metodo_pago', 'efectivo').strip()

    try:
        sim.estado = 'Vendida'
        sim.vendedor_id = current_user.id
        sim.metodo_pago = metodo_pago
        sim.precio_venta_real = precio_venta_real
        sim.fecha_venta = obtener_hora_bogota()
        
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': 'Error de base de datos al registrar la venta.'}), 500

@sims_bp.route('/cambiar-estado/<int:sim_id>', methods=['POST'])
@login_required
def cambiar_estado(sim_id):
    sim = SimCard.query.get_or_404(sim_id)
    nuevo_estado = request.form.get('nuevo_estado', '').strip()

    if nuevo_estado not in ['Disponible', 'Dañada']:
        return jsonify({'success': False, 'error': 'Estado inválido desde esta acción (para Ventas usa el botón Vender).'}), 400

    if sim.estado == 'Vendida':
        return jsonify({'success': False, 'error': 'No se puede cambiar el estado de un chip vendido desde aquí.'}), 400

    try:
        sim.estado = nuevo_estado
        db.session.commit()
        return jsonify({'success': True, 'nuevo_estado': nuevo_estado})
    except Exception:
        db.session.rollback()
        return jsonify({'success': False, 'error': 'Error al actualizar el estado.'}), 500

@sims_bp.route('/revertir-venta/<int:sim_id>', methods=['POST'])
@login_required
@admin_required
def revertir_venta(sim_id):
    sim = SimCard.query.get_or_404(sim_id)
    
    if sim.estado != 'Vendida':
        flash('Esta SIM no está registrada como vendida.', 'warning')
        return redirect(url_for('sims_bp.index'))

    try:
        sim.estado = 'Disponible'
        sim.vendedor_id = None
        sim.metodo_pago = None
        sim.precio_venta_real = None
        sim.fecha_venta = None
        
        db.session.commit()
        flash(f'Venta de SIM con línea {sim.numero_telefono} revertida correctamente. El chip vuelve a estar Disponible.', 'success')
    except Exception:
        db.session.rollback()
        flash('Error al intentar revertir la venta de la SIM.', 'danger')
        
    return redirect(url_for('sims_bp.index'))

@sims_bp.route('/editar/<int:sim_id>', methods=['POST'])
@login_required
def editar(sim_id):
    sim = SimCard.query.get_or_404(sim_id)
    
    sim.numero_telefono = request.form.get('numero_telefono', sim.numero_telefono).strip()
    sim.iccid = request.form.get('iccid', sim.iccid).strip()
    sim.operador = request.form.get('operador', sim.operador).strip()
    sim.precio_costo = float(request.form.get('precio_costo', sim.precio_costo) or 0.0)
    sim.precio_venta = float(request.form.get('precio_venta', sim.precio_venta) or 0.0)
    sim.observacion = request.form.get('observacion', sim.observacion).strip()

    try:
        db.session.commit()
        flash(f'SIM con línea {sim.numero_telefono} actualizada correctamente.', 'success')
    except Exception:
        db.session.rollback()
        flash('Error al actualizar los datos de la SIM.', 'danger')
        
    return redirect(url_for('sims_bp.index'))

@sims_bp.route('/eliminar/<int:sim_id>', methods=['POST'])
@login_required
@admin_required
def eliminar(sim_id):
    sim = SimCard.query.get_or_404(sim_id)
    
    if sim.estado == 'Vendida':
        flash('Acción denegada: No se puede eliminar una SIM que ya ha sido vendida.', 'warning')
        return redirect(url_for('sims_bp.index'))

    try:
        numero = sim.numero_telefono
        db.session.delete(sim)
        db.session.commit()
        flash(f'SIM con línea {numero} eliminada exitosamente.', 'success')
    except Exception:
        db.session.rollback()
        flash('Error en servidor al eliminar la SIM.', 'danger')
        
    return redirect(url_for('sims_bp.index'))
