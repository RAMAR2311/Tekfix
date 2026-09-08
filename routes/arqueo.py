# pyright: reportCallIssue=false
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, Sale, SalePayment, ArqueoCaja, Expense, SimCard
from decorators import admin_required
from datetime import datetime, date
from decimal import Decimal
import pytz

arqueo_bp = Blueprint('arqueo_bp', __name__)

def obtener_hora_bogota():
    return datetime.now(pytz.timezone('America/Bogota')).replace(tzinfo=None)

def calcular_totales_y_desglose(ventas_del_dia, sims_del_dia):
    """Calcula los totales de efectivo, transferencias y desglose de billeteras digitales."""
    total_efectivo = Decimal('0')
    total_transferencia = Decimal('0')
    desglose_digital = {
        'nequi': Decimal('0'),
        'bancolombia': Decimal('0'),
        'daviplata': Decimal('0'),
        'tarjeta': Decimal('0'),
        'credito': Decimal('0'),
        'otros': Decimal('0')
    }

    def sumar_metodo(metodo, monto):
        nonlocal total_efectivo, total_transferencia
        monto = Decimal(str(monto or 0))
        m = (metodo or '').strip().lower()
        if m == 'efectivo':
            total_efectivo += monto
        else:
            total_transferencia += monto
            if 'nequi' in m:
                desglose_digital['nequi'] += monto
            elif 'bancolombia' in m:
                desglose_digital['bancolombia'] += monto
            elif 'daviplata' in m:
                desglose_digital['daviplata'] += monto
            elif any(k in m for k in ['tarjeta', 'datafono', 'datáfono', 'bolt']):
                desglose_digital['tarjeta'] += monto
            elif 'credito' in m or 'crédito' in m:
                desglose_digital['credito'] += monto
            else:
                desglose_digital['otros'] += monto

    for v in ventas_del_dia:
        if v.pagos:
            for p in v.pagos:
                sumar_metodo(p.metodo_pago, p.monto)
        else:
            sumar_metodo(v.metodo_pago, v.monto_total)

    for sim in sims_del_dia:
        sumar_metodo(sim.metodo_pago, sim.precio_venta_real)

    return total_efectivo, total_transferencia, desglose_digital

@arqueo_bp.route('/')
@login_required
def index():
    return redirect(url_for('arqueo_bp.nuevo'))

@arqueo_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo():
    hoy = obtener_hora_bogota().date()
    
    # REGLA DE SEGURIDAD: El vendedor SOLO puede ver y operar el arqueo del día de hoy
    if current_user.rol != 'admin':
        fecha_seleccionada = hoy
        fecha_str = hoy.strftime('%Y-%m-%d')
    else:
        fecha_str = request.args.get('fecha', hoy.strftime('%Y-%m-%d'))
        try:
            fecha_seleccionada = datetime.strptime(fecha_str, '%Y-%m-%d').date()
        except ValueError:
            fecha_seleccionada = hoy
            fecha_str = fecha_seleccionada.strftime('%Y-%m-%d')

    # Calcular ventas y SIMs del día
    ventas_del_dia = Sale.query.filter(db.func.date(Sale.fecha_venta) == fecha_seleccionada).all()
    sims_vendidas = SimCard.query.filter(
        db.func.date(SimCard.fecha_venta) == fecha_seleccionada,
        SimCard.estado == 'Vendida'
    ).all()

    total_efectivo, total_transferencia, desglose_digital = calcular_totales_y_desglose(ventas_del_dia, sims_vendidas)

    # Calcular gastos automáticos del día y cargar lista detallada
    gastos_diarios_registros = Expense.query.filter(
        db.func.date(Expense.fecha_gasto) == fecha_seleccionada,
        Expense.tipo_gasto == 'Gasto Diario'
    ).order_by(Expense.fecha_gasto.asc()).all()
    gastos_automaticos = float(sum(g.monto for g in gastos_diarios_registros))

    # Verificar si ya existe un arqueo para esa fecha en el sistema (Caja Única Global)
    arqueo_existente = ArqueoCaja.query.filter_by(fecha_arqueo=fecha_seleccionada).first()

    if request.method == 'POST':
        if arqueo_existente:
            flash('Este arqueo ya fue cerrado previamente y no puede modificarse.', 'warning')
            return redirect(url_for('arqueo_bp.nuevo'))

        base_inicial = float(request.form.get('base_inicial', 0.0))
        
        # Recalcular gastos automáticos por seguridad en el backend
        gastos_recalculados = Expense.query.filter(
            db.func.date(Expense.fecha_gasto) == fecha_seleccionada,
            Expense.tipo_gasto == 'Gasto Diario'
        ).all()
        gastos_del_dia = float(sum(g.monto for g in gastos_recalculados))
        
        observaciones_gastos = request.form.get('observaciones_gastos', '').strip()
        efectivo_fisico = float(request.form.get('efectivo_fisico', 0.0))
        observacion_diferencia = request.form.get('observacion_diferencia', '').strip()

        # Calcular diferencia para el reporte
        esperado = (base_inicial + float(total_efectivo)) - gastos_del_dia
        diferencia = efectivo_fisico - esperado

        nuevo_arqueo = ArqueoCaja(
            vendedor_id=current_user.id,
            fecha_arqueo=fecha_seleccionada,
            base_inicial=base_inicial,
            gastos_del_dia=gastos_del_dia,
            observaciones_gastos=observaciones_gastos,
            total_efectivo_sistema=total_efectivo,
            total_transferencia_sistema=total_transferencia,
            efectivo_fisico=efectivo_fisico,
            diferencia=diferencia,
            observacion_diferencia=observacion_diferencia
        )

        try:
            db.session.add(nuevo_arqueo)
            db.session.commit()
            perfil_label = 'Administrador' if current_user.rol == 'admin' else 'Vendedor'
            flash(
                f'✅ Arqueo de caja guardado exitosamente. '
                f'Cierre realizado por <strong>{current_user.nombre}</strong> '
                f'({perfil_label}) el {fecha_str}.',
                'success'
            )
            if current_user.rol == 'admin':
                return redirect(url_for('arqueo_bp.reporte', fecha_inicio=fecha_str, fecha_fin=fecha_str))
            else:
                return redirect(url_for('arqueo_bp.nuevo'))
        except Exception as e:
            db.session.rollback()
            flash('Ocurrió un error al guardar el arqueo de caja.', 'danger')

    # Ordenar ventas del día por hora para mostrar en el formulario
    ventas_del_dia_ordenadas = Sale.query.filter(
        db.func.date(Sale.fecha_venta) == fecha_seleccionada
    ).order_by(Sale.fecha_venta.asc()).all()

    return render_template(
        'arqueo/form.html',
        fecha=fecha_str,
        total_efectivo=float(total_efectivo or 0),
        total_transferencia=float(total_transferencia or 0),
        desglose_digital={k: float(v or 0) for k, v in desglose_digital.items()},
        arqueo_existente=arqueo_existente,
        gastos_automaticos=float(gastos_automaticos or 0),
        gastos_diarios_registros=gastos_diarios_registros,
        ventas_del_dia=ventas_del_dia_ordenadas,
        sims_del_dia=sims_vendidas
    )

@arqueo_bp.route('/reporte', methods=['GET'])
@login_required
def reporte():
    # REGLA DE SEGURIDAD: Los vendedores no tienen acceso al histórico de arqueos ya cerrados
    if current_user.rol != 'admin':
        flash('Acceso restringido: Los arqueos ya cerrados solo pueden ser consultados por el Administrador.', 'warning')
        return redirect(url_for('arqueo_bp.nuevo'))

    fecha_inicio_str = request.args.get('fecha_inicio', obtener_hora_bogota().strftime('%Y-%m-%d'))
    fecha_fin_str = request.args.get('fecha_fin', obtener_hora_bogota().strftime('%Y-%m-%d'))

    try:
        fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date()
        fecha_fin = datetime.strptime(fecha_fin_str, '%Y-%m-%d').date()
    except ValueError:
        fecha_inicio = obtener_hora_bogota().date()
        fecha_fin = obtener_hora_bogota().date()

    # Al ser una caja única global, todos los usuarios autorizados ven los mismos arqueos
    query = ArqueoCaja.query.filter(ArqueoCaja.fecha_arqueo >= fecha_inicio, ArqueoCaja.fecha_arqueo <= fecha_fin)

    arqueos = query.order_by(ArqueoCaja.fecha_arqueo.desc()).all()

    # Cálculos globales para el reporte
    resumen = {
        'total_base': float(sum(a.base_inicial or 0 for a in arqueos)),
        'total_efectivo': float(sum(a.total_efectivo_sistema or 0 for a in arqueos)),
        'total_transferencia': float(sum(a.total_transferencia_sistema or 0 for a in arqueos)),
        'total_gastos': float(sum(a.gastos_del_dia or 0 for a in arqueos))
    }
    
    resumen['total_recaudado'] = resumen['total_efectivo'] + resumen['total_transferencia']
    resumen['efectivo_esperado'] = (resumen['total_base'] + resumen['total_efectivo']) - resumen['total_gastos']

    # Obtener todas las ventas consolidadas del periodo para el detalle en la "tirilla" (sin filtrar por vendedor)
    ventas_query = Sale.query.filter(
        db.func.date(Sale.fecha_venta) >= fecha_inicio,
        db.func.date(Sale.fecha_venta) <= fecha_fin
    )
    
    ventas_periodo = ventas_query.order_by(Sale.fecha_venta.asc()).all()

    fecha_generacion = obtener_hora_bogota().strftime('%Y-%m-%d %H:%M')

    return render_template(
        'arqueo/reporte.html',
        arqueos=arqueos,
        resumen=resumen,
        fecha_inicio=fecha_inicio_str,
        fecha_fin=fecha_fin_str,
        fecha_generacion=fecha_generacion,
        ventas_periodo=ventas_periodo
    )

@arqueo_bp.route('/sobrantes', methods=['GET'])
@login_required
@admin_required
def sobrantes():
    # Solo mostrar arqueos donde la diferencia sea mayor a 0
    historial_sobrantes = ArqueoCaja.query.filter(ArqueoCaja.diferencia > 0).order_by(ArqueoCaja.fecha_arqueo.desc()).all()
    
    total_acumulado = sum(s.diferencia for s in historial_sobrantes)
    
    return render_template(
        'arqueo/sobrantes.html',
        sobrantes=historial_sobrantes,
        total_acumulado=total_acumulado
    )
