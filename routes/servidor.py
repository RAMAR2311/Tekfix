# pyright: reportCallIssue=false
import os
import urllib.parse
from datetime import datetime
from itsdangerous import URLSafeTimedSerializer
import pytz

from flask import Blueprint, render_template, request, current_app
from models import db, ServerPayment

servidor_bp = Blueprint('servidor_bp', __name__)

MESES_ES = [
    '', 'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
    'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'
]

def obtener_hora_bogota():
    return datetime.now(pytz.timezone('America/Bogota')).replace(tzinfo=None)

def obtener_serializer(secret_key=None):
    key = secret_key or current_app.config.get('SECRET_KEY', 'dev-key-super-secreta')
    return URLSafeTimedSerializer(key, salt='server-payment-salt')

def calcular_info_pago_servidor(app):
    """Calcula el estado del pago del servidor y estructura de contexto global."""
    try:
        hoy = obtener_hora_bogota().date()
    except Exception:
        hoy = datetime.now().date()

    anio_actual = hoy.year
    mes_actual = hoy.month
    dia_actual = hoy.day

    mes_nombre = MESES_ES[mes_actual] if 1 <= mes_actual <= 12 else str(mes_actual)
    monto_mensual = os.environ.get('VALOR_MENSUALIDAD_SERVIDOR', '50.000')

    # Verificar si ya existe registro pagado para el año y mes actual
    try:
        pago_db = ServerPayment.query.filter_by(
            anio=anio_actual,
            mes=mes_actual,
            estado='pagado'
        ).first()
    except Exception:
        pago_db = None

    # Generar Token firmado con itsdangerous
    secret_key = app.config.get('SECRET_KEY', 'dev-key-super-secreta')
    s = URLSafeTimedSerializer(secret_key, salt='server-payment-salt')
    token = s.dumps({'anio': anio_actual, 'mes': mes_actual})

    # Host y URL de confirmación
    host = 'http://localhost:5000'
    try:
        if request:
            host = request.host_url.rstrip('/')
    except Exception:
        pass

    confirm_url = f"{host}/servidor/confirmar-pago?token={token}"

    # Mensaje y URL de WhatsApp
    msg_whatsapp = (
        f"Hola, adjunto el comprobante de pago de la mensualidad del servidor Zenic "
        f"(${monto_mensual} COP) para {mes_nombre} {anio_actual}.\n\n"
        f"Para confirmar mi pago en el sistema con 1 solo clic, toca aquí:\n{confirm_url}"
    )
    whatsapp_url = f"https://wa.me/573115643557?text={urllib.parse.quote(msg_whatsapp)}"

    # Evaluación del calendario:
    # Si ya está pagado en la BD: estado = 'pagado'
    # Días 1 al 6: estado = 'al_dia'
    # Días 7 al 14: estado = 'preventivo' (faltan X días para el 15)
    # Día 15: estado = 'hoy' (día exacto de vencimiento)
    # Días 16 al 20: estado = 'gabela' (período de gracia de 5 días; calcula dias_gabela = 20 - dia_actual + 1)
    # Día 21 en adelante: estado = 'vencido' (gabela de 5 días agotada)
    dias_restantes = max(0, 15 - dia_actual)
    dias_gabela = max(0, 20 - dia_actual + 1) if dia_actual >= 16 else 5

    if pago_db:
        estado = 'pagado'
    elif 1 <= dia_actual <= 6:
        estado = 'al_dia'
    elif 7 <= dia_actual <= 14:
        estado = 'preventivo'
    elif dia_actual == 15:
        estado = 'hoy'
    elif 16 <= dia_actual <= 20:
        estado = 'gabela'
    else:
        estado = 'vencido'

    return {
        'estado': estado,
        'mes_nombre': mes_nombre,
        'mes': mes_actual,
        'anio': anio_actual,
        'dia_actual': dia_actual,
        'monto': monto_mensual,
        'dias_restantes': dias_restantes,
        'dias_gabela': dias_gabela,
        'whatsapp_url': whatsapp_url,
        'confirm_url': confirm_url,
        'nu_llave': '@QEI910',
        'nequi_num': '3505422186',
        'fecha_vencimiento_str': f"15 de {mes_nombre} {anio_actual}",
        'esta_pagado': bool(pago_db)
    }

@servidor_bp.route('/confirmar-pago', methods=['GET', 'POST'])
def confirmar_pago():
    token = request.args.get('token') or request.form.get('token')
    if not token:
        return render_template('servidor/confirmar_pago.html', error='No se proporcionó el token de confirmación de pago.'), 400

    s = obtener_serializer(current_app.config.get('SECRET_KEY'))
    try:
        data = s.loads(token)
        anio = int(data.get('anio'))
        mes = int(data.get('mes'))
        mes_nombre = MESES_ES[mes] if 1 <= mes <= 12 else str(mes)
    except Exception:
        return render_template(
            'servidor/confirmar_pago.html',
            error='El token de confirmación de pago es inválido, ha caducado o está adulterado.',
            token=token
        ), 400

    # Verificar si ya está pagado
    pago_existente = ServerPayment.query.filter_by(anio=anio, mes=mes, estado='pagado').first()
    if pago_existente:
        return render_template(
            'servidor/confirmar_pago.html',
            ya_confirmado=True,
            anio=anio,
            mes=mes,
            mes_nombre=mes_nombre,
            fecha_pago=pago_existente.fecha_pago,
            token=token
        )

    # Procesar solicitud POST (Confirmación con PIN)
    if request.method == 'POST':
        pin_ingresado = (request.form.get('pin') or '').strip()
        pin_secreto = os.environ.get('PIN_CONFIRMACION_SERVIDOR', '9876').strip()

        if pin_ingresado == pin_secreto:
            # Registrar o actualizar pago en BD
            pago = ServerPayment.query.filter_by(anio=anio, mes=mes).first()
            ahora = obtener_hora_bogota()
            if not pago:
                pago = ServerPayment(
                    anio=anio,
                    mes=mes,
                    estado='pagado',
                    fecha_pago=ahora,
                    observacion='Confirmado exitosamente vía Token WhatsApp + PIN Proveedor'
                )
                db.session.add(pago)
            else:
                pago.estado = 'pagado'
                pago.fecha_pago = ahora
                pago.observacion = 'Confirmado exitosamente vía Token WhatsApp + PIN Proveedor'

            try:
                db.session.commit()
                return render_template(
                    'servidor/confirmar_pago.html',
                    exito=True,
                    anio=anio,
                    mes=mes,
                    mes_nombre=mes_nombre,
                    fecha_pago=ahora,
                    token=token
                )
            except Exception as e:
                db.session.rollback()
                return render_template(
                    'servidor/confirmar_pago.html',
                    error=f'Error en base de datos al guardar la confirmación: {e}',
                    token=token
                ), 500
        else:
            # PIN erróneo
            return render_template(
                'servidor/confirmar_pago.html',
                formulario_pin=True,
                pin_error=True,
                anio=anio,
                mes=mes,
                mes_nombre=mes_nombre,
                token=token
            )

    # Solicitud GET inicial: formulario pidiendo PIN
    return render_template(
        'servidor/confirmar_pago.html',
        formulario_pin=True,
        anio=anio,
        mes=mes,
        mes_nombre=mes_nombre,
        token=token
    )
