import os
from app import create_app
from models import db, ArqueoCaja, User
from datetime import date, timedelta
from decimal import Decimal

def forzar():
    app = create_app()
    # Forzar la URL de conexión que funcionó
    app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:admin123@localhost:5432/Tekfix'
    
    with app.app_context():
        print("--- INICIANDO CREACIÓN FORZADA DE EJEMPLOS ---")
        
        # 1. Buscar al administrador maestro o el primero
        user = User.query.filter_by(rol='admin').first() or User.query.first()
        if not user:
            print("ERROR: No se encontró ningún usuario.")
            return

        print(f"Usando usuario: {user.nombre} ({user.email})")

        # 2. Definir fechas de los ejemplos
        fechas = [date.today(), date.today() - timedelta(days=1), date.today() - timedelta(days=2)]
        
        # 3. Limpiar arqueos viejos en esas fechas para este usuario
        for f in fechas:
            ArqueoCaja.query.filter_by(fecha_arqueo=f, vendedor_id=user.id).delete()
        
        db.session.commit()

        # 4. Crear los 3 ejemplos con SOBRANTE CLARO
        ejemplos = [
            {"fecha": fechas[0], "base": 100000, "sistema": 500000, "gastos": 0, "fisico": 650000, "obs": "Sobrante de hoy: El cliente dejó la vuelta de un accesorio caro como propina."},
            {"fecha": fechas[1], "base": 120000, "sistema": 400000, "gastos": 20000, "fisico": 580000, "obs": "Sobrante ayer: Se encontró dinero extra al fondo de la caja al finalizar el turno."},
            {"fecha": fechas[2], "base": 100000, "sistema": 300000, "gastos": 50000, "fisico": 450000, "obs": "Sobrante hace 2 días: Pago de un servicio técnico que no se había registrado."}
        ]

        for ej in ejemplos:
            esperado = (ej["base"] + ej["sistema"]) - ej["gastos"]
            dif = ej["fisico"] - esperado
            
            nuevo = ArqueoCaja(
                vendedor_id=user.id,
                fecha_arqueo=ej["fecha"],
                base_inicial=Decimal(str(ej["base"])),
                total_efectivo_sistema=Decimal(str(ej["sistema"])),
                total_transferencia_sistema=Decimal("0.00"),
                gastos_del_dia=Decimal(str(ej["gastos"])),
                efectivo_fisico=Decimal(str(ej["fisico"])),
                diferencia=Decimal(str(dif)),
                observacion_diferencia=ej["obs"]
            )
            db.session.add(nuevo)
            print(f"Creado: {ej['fecha']} con sobrante de +${dif}")

        db.session.commit()
        print("\n--- ¡ÉXITO! Ejemplos inyectados correctamente. ---")

if __name__ == "__main__":
    forzar()
