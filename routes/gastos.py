from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, Expense, obtener_hora_bogota
from decorators import admin_required
from sqlalchemy import extract
from datetime import datetime

gastos_bp = Blueprint('gastos_bp', __name__)

@gastos_bp.route('/', methods=['GET', 'POST'])
@login_required
def index():
    if request.method == 'POST':
        tipo_gasto = request.form.get('tipo_gasto')
        
        # Restricción de seguridad backend: Vendedores sólo registran gastos operativos
        if current_user.rol != 'admin':
            tipo_gasto = 'Gasto Diario'
            
        categoria = request.form.get('categoria')
        descripcion = request.form.get('descripcion')
        monto = float(request.form.get('monto', 0))
        fecha_str = request.form.get('fecha_gasto')

        # Use the provided date or fallback to current datetime
        if fecha_str:
            try:
                # El front devuelve yy-mm-dd si se uso <input type="date">
                fecha_obj = datetime.strptime(fecha_str, '%Y-%m-%d')
            except ValueError:
                fecha_obj = obtener_hora_bogota()
        else:
            fecha_obj = obtener_hora_bogota()

        try:
            nuevo_gasto = Expense(
                usuario_id=current_user.id,
                tipo_gasto=tipo_gasto,
                categoria=categoria,
                descripcion=descripcion,
                monto=monto,
                fecha_gasto=fecha_obj
            )
            db.session.add(nuevo_gasto)
            db.session.commit()
            flash('Gasto registrado exitosamente.', 'success')
        except Exception as e:
            db.session.rollback()
            flash('Error al intentar registrar el gasto en la base de datos.', 'danger')
        
        return redirect(url_for('gastos_bp.index'))

    # GET Logic (Filters selected month expenses)
    mes_str = request.args.get('mes')
    hoy = obtener_hora_bogota()
    
    if mes_str:
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
    
    # Mapeo de meses en español
    meses_es = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
    nombre_mes = meses_es[inicio_mes.month - 1]

    # Consultamos registros del mes seleccionado
    query = Expense.query.filter(
        Expense.fecha_gasto >= inicio_mes,
        Expense.fecha_gasto < fin_mes
    )
    
    # Restricción de visibilidad: 
    # Si no es administrador, SOLAMENTE puede ver los gastos que haya registrado él mismo.
    if current_user.rol != 'admin':
        query = query.filter(Expense.usuario_id == current_user.id)
        
    gastos_mes = query.order_by(Expense.fecha_gasto.desc()).all()

    total_diarios = sum((g.monto for g in gastos_mes if g.tipo_gasto == 'Gasto Diario'))
    total_indirectos = sum((g.monto for g in gastos_mes if g.tipo_gasto == 'Costo Indirecto'))
    total_mes = total_diarios + total_indirectos

    # Agrupar egresos por categorías de manera ordenada
    from decimal import Decimal
    desglose_raw = {}
    for g in gastos_mes:
        cat = g.categoria.strip().title()
        if cat not in desglose_raw:
            desglose_raw[cat] = {
                'total': Decimal('0.00'),
                'tipo_gasto': g.tipo_gasto,
                'cantidad': 0
            }
        desglose_raw[cat]['total'] += g.monto
        desglose_raw[cat]['cantidad'] += 1
        
    # Calcular porcentajes y ordenar de mayor a menor monto
    desglose_categorias = []
    for cat, info in desglose_raw.items():
        porcentaje = 0.0
        if total_mes > 0:
            porcentaje = round((float(info['total']) / float(total_mes)) * 100, 1)
        desglose_categorias.append({
            'nombre': cat,
            'total': info['total'],
            'tipo_gasto': info['tipo_gasto'],
            'cantidad': info['cantidad'],
            'porcentaje': porcentaje
        })
        
    # Ordenar por el total gastado de forma descendente
    desglose_categorias = sorted(desglose_categorias, key=lambda x: x['total'], reverse=True)

    # Provide today's date formatted for HTML5 <input type="date">
    hoy_str = hoy.strftime('%Y-%m-%d')
    return render_template('gastos/index.html', 
                           gastos=gastos_mes, 
                           total_diarios=total_diarios, 
                           total_indirectos=total_indirectos, 
                           desglose_categorias=desglose_categorias,
                           mes_seleccionado=mes_seleccionado,
                           nombre_mes=nombre_mes,
                           hoy=hoy_str)

@gastos_bp.route('/eliminar/<int:id>', methods=['POST'])
@login_required
def eliminar_gasto(id):
    gasto = Expense.query.get_or_404(id)
    
    # Restricción: Solo Admin o el usuario que lo creó
    if current_user.rol != 'admin' and gasto.usuario_id != current_user.id:
        flash('No tienes permiso para eliminar este gasto.', 'danger')
        return redirect(url_for('gastos_bp.index'))
    
    try:
        db.session.delete(gasto)
        db.session.commit()
        flash('Gasto eliminado correctamente.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error al intentar eliminar el gasto.', 'danger')
        
    return redirect(url_for('gastos_bp.index'))
