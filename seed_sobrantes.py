import os
from app import create_app
from models import db, ArqueoCaja, User
from datetime import date, timedelta
from decimal import Decimal

def seed_sobrantes():
    app = create_app()
    app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:admin123@127.0.0.1:5432/Tekfix'
    with app.app_context():
        print("Generando ejemplos de sobrantes...")
        
        # Obtener un usuario (preferiblemente admin)
        user = User.query.filter_by(rol='admin').first() or User.query.first()
        if not user:
            print("Error: No hay usuarios para asociar los arqueos.")
            return

        # Datos de ejemplo
        ejemplos = [
            {
                "fecha": date.today() - timedelta(days=2),
                "base": 100000,
                "efectivo_sistema": 450000,
                "gastos": 25000,
                "fisico": 550000,
                "obs_gastos": "Pago de flete servientrega",
                "obs_dif": "Sobrante por propina de cliente y redondeo de facturas del día."
            },
            {
                "fecha": date.today() - timedelta(days=1),
                "base": 150000,
                "efectivo_sistema": 320000,
                "gastos": 0,
                "fisico": 485000,
                "obs_gastos": "",
                "obs_dif": "Se encontró billete de 15.000 que no estaba registrado en ninguna venta. Se presume error en registro de venta de accesorio."
            },
            {
                "fecha": date.today(),
                "base": 120000,
                "efectivo_sistema": 680000,
                "gastos": 50000,
                "fisico": 770000,
                "obs_gastos": "Reparación de cerradura local",
                "obs_dif": "Sobrante de caja tras recibir pago de deuda antigua no contabilizada en sistema por el cliente Don Pedro."
            }
        ]

        for item in ejemplos:
            # Evitar duplicados para la misma fecha y usuario
            existente = ArqueoCaja.query.filter_by(fecha_arqueo=item["fecha"], vendedor_id=user.id).first()
            if existente:
                print(f"Ya existe arqueo para {item['fecha']}, saltando...")
                continue

            esperado = (item["base"] + item["efectivo_sistema"]) - item["gastos"]
            diferencia = item["fisico"] - esperado
            
            nuevo = ArqueoCaja(
                vendedor_id=user.id,
                fecha_arqueo=item["fecha"],
                base_inicial=Decimal(str(item["base"])),
                total_efectivo_sistema=Decimal(str(item["efectivo_sistema"])),
                total_transferencia_sistema=Decimal("0.00"),
                gastos_del_dia=Decimal(str(item["gastos"])),
                observaciones_gastos=item["obs_gastos"],
                efectivo_fisico=Decimal(str(item["fisico"])),
                diferencia=Decimal(str(diferencia)),
                observacion_diferencia=item["obs_dif"]
            )
            db.session.add(nuevo)
        
        db.session.commit()
        print("[OK] 3 ejemplos de sobrantes creados con éxito.")

if __name__ == '__main__':
    seed_sobrantes()
