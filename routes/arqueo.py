from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, Sale, ArqueoCaja, Expense
from decorators import admin_required
from datetime import datetime, date
import pytz

arqueo_bp = Blueprint('arqueo_bp', __name__)

def obtener_hora_bogota():
    return datetime.now(pytz.timezone('America/Bogota')).replace(tzinfo=None)

@arqueo_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo():
    # Obtener fecha de la URL o usar hoy
    fecha_str = request.args.get('fecha', obtener_hora_bogota().strftime('%Y-%m-%d'))
    try:
        fecha_seleccionada = datetime.strptime(fecha_str, '%Y-%m-%d').date()
    except ValueError:
        fecha_seleccionada = obtener_hora_bogota().date()
        fecha_str = fecha_seleccionada.strftime('%Y-%m-%d')

    # Calcular ventas del día
    ventas_del_dia = Sale.query.filter(db.func.date(Sale.fecha_venta) == fecha_seleccionada).all()
    
    total_efectivo = sum(v.monto_total for v in ventas_del_dia if v.metodo_pago == 'efectivo')
    total_transferencia = sum(v.monto_total for v in ventas_del_dia if v.metodo_pago == 'transferencia')

    # Calcular gastos automáticos del día
    gastos_diarios_registros = Expense.query.filter(
        db.func.date(Expense.fecha_gasto) == fecha_seleccionada,
        Expense.tipo_gasto == 'Gasto Diario'
    ).all()
    gastos_automaticos = float(sum(g.monto for g in gastos_diarios_registros))

    # Verificar si ya existe arqueo para esa fecha por este vendedor (Opcional, pero recomendado)
    arqueo_existente = ArqueoCaja.query.filter_by(fecha_arqueo=fecha_seleccionada, vendedor_id=current_user.id).first()

    if request.method == 'POST':
        base_inicial = float(request.form.get('base_inicial', 0.0))
        
        # Recalcular gastos automáticos por seguridad en el backend
        gastos_recalculados = Expense.query.filter(
            db.func.date(Expense.fecha_gasto) == fecha_seleccionada,
            Expense.tipo_gasto == 'Gasto Diario'
        ).all()
        gastos_del_dia = float(sum(g.monto for g in gastos_recalculados))
        
        observaciones_gastos = request.form.get('observaciones_gastos', '').strip()

        nuevo_arqueo = ArqueoCaja(
            vendedor_id=current_user.id,
            fecha_arqueo=fecha_seleccionada,
            base_inicial=base_inicial,
            gastos_del_dia=gastos_del_dia,
            observaciones_gastos=observaciones_gastos,
            total_efectivo_sistema=total_efectivo,
            total_transferencia_sistema=total_transferencia
        )

        try:
            db.session.add(nuevo_arqueo)
            db.session.commit()
            flash('Arqueo de caja guardado exitosamente.', 'success')
            return redirect(url_for('arqueo_bp.reporte', fecha_inicio=fecha_str, fecha_fin=fecha_str))
        except Exception as e:
            db.session.rollback()
            flash('Ocurrió un error al guardar el arqueo de caja.', 'danger')

    return render_template(
        'arqueo/form.html',
        fecha=fecha_str,
        total_efectivo=total_efectivo,
        total_transferencia=total_transferencia,
        arqueo_existente=arqueo_existente,
        gastos_automaticos=gastos_automaticos
    )

@arqueo_bp.route('/reporte', methods=['GET'])
@login_required
def reporte():
    fecha_inicio_str = request.args.get('fecha_inicio', obtener_hora_bogota().strftime('%Y-%m-%d'))
    fecha_fin_str = request.args.get('fecha_fin', obtener_hora_bogota().strftime('%Y-%m-%d'))

    try:
        fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date()
        fecha_fin = datetime.strptime(fecha_fin_str, '%Y-%m-%d').date()
    except ValueError:
        fecha_inicio = obtener_hora_bogota().date()
        fecha_fin = obtener_hora_bogota().date()

    # Si es admin puede ver todos los arqueos, si no, solo los suyos
    query = ArqueoCaja.query.filter(ArqueoCaja.fecha_arqueo >= fecha_inicio, ArqueoCaja.fecha_arqueo <= fecha_fin)
    
    if current_user.rol != 'admin':
        query = query.filter(ArqueoCaja.vendedor_id == current_user.id)

    arqueos = query.order_by(ArqueoCaja.fecha_arqueo.desc()).all()

    # Cálculos globales para el reporte
    resumen = {
        'total_base': sum(a.base_inicial for a in arqueos),
        'total_efectivo': sum(a.total_efectivo_sistema for a in arqueos),
        'total_transferencia': sum(a.total_transferencia_sistema for a in arqueos),
        'total_gastos': sum(a.gastos_del_dia for a in arqueos)
    }
    
    resumen['total_recaudado'] = resumen['total_efectivo'] + resumen['total_transferencia']
    resumen['efectivo_esperado'] = (resumen['total_base'] + resumen['total_efectivo']) - resumen['total_gastos']

    fecha_generacion = obtener_hora_bogota().strftime('%Y-%m-%d %H:%M')

    return render_template(
        'arqueo/reporte.html',
        arqueos=arqueos,
        resumen=resumen,
        fecha_inicio=fecha_inicio_str,
        fecha_fin=fecha_fin_str,
        fecha_generacion=fecha_generacion
    )
