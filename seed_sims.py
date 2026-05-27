# pyright: reportCallIssue=false
from app import create_app
from models import db, SimCard
from decimal import Decimal

def seed_sims():
    app = create_app()
    with app.app_context():
        print("=== INICIALIZANDO CREACIÓN DE TABLAS Y SEMILLA DE SIMS ===")
        
        # 1. Crear tabla sim_cards si no existe (db.create_all lo hace automáticamente)
        db.create_all()
        print("[OK] Tabla 'sim_cards' creada o verificada en la base de datos.")

        # 2. Limpiar registros de prueba anteriores
        SimCard.query.delete()
        db.session.commit()
        print("[OK] Limpieza de SIMs anteriores realizada.")

        # 3. Inyectar registros de prueba
        from models import User, obtener_hora_bogota
        vendedor = User.query.first()
        vendedor_id = vendedor.id if vendedor else None
        hoy = obtener_hora_bogota()

        sims_data = [
            # SIMs Claro
            {"num": "3104561234", "icc": "8957101000000000001", "op": "Claro", "costo": 2000.0, "venta": 5000.0, "estado": "Disponible"},
            {"num": "3118904321", "icc": "8957101000000000002", "op": "Claro", "costo": 2000.0, "venta": 5000.0, "estado": "Disponible"},
            {"num": "3127650987", "icc": "8957101000000000003", "op": "Claro", "costo": 2000.0, "venta": 5000.0, "estado": "Vendida", "pago": "nequi", "real": 5000.0, "fecha": hoy},
            
            # SIMs Tigo
            {"num": "3004325678", "icc": "8957102000000000001", "op": "Tigo", "costo": 3000.0, "venta": 8000.0, "estado": "Disponible"},
            {"num": "3019875432", "icc": "8957102000000000002", "op": "Tigo", "costo": 3000.0, "venta": 8000.0, "estado": "Dañada"},

            # SIMs Movistar
            {"num": "3156543210", "icc": "8957103000000000001", "op": "Movistar", "costo": 2500.0, "venta": 6000.0, "estado": "Disponible"},
            {"num": "3167890123", "icc": "8957103000000000002", "op": "Movistar", "costo": 2500.0, "venta": 6000.0, "estado": "Vendida", "pago": "efectivo", "real": 6000.0, "fecha": hoy},

            # SIMs Wom
            {"num": "3023210987", "icc": "8957104000000000001", "op": "Wom", "costo": 1500.0, "venta": 4000.0, "estado": "Disponible"},
            {"num": "3059876543", "icc": "8957104000000000002", "op": "Wom", "costo": 1500.0, "venta": 4000.0, "estado": "Disponible"}
        ]

        for s in sims_data:
            nueva_sim = SimCard(
                numero_telefono=s["num"],
                iccid=s["icc"],
                operador=s["op"],
                precio_costo=Decimal(str(s["costo"])),
                precio_venta=Decimal(str(s["venta"])),
                estado=s["estado"],
                observacion=f"SIM de prueba autoinyectada para {s['op']}"
            )
            if s["estado"] == "Vendida":
                nueva_sim.vendedor_id = vendedor_id
                nueva_sim.metodo_pago = s["pago"]
                nueva_sim.precio_venta_real = Decimal(str(s["real"]))
                nueva_sim.fecha_venta = s["fecha"]
                
            db.session.add(nueva_sim)
        
        db.session.commit()
        print("[OK] SIMs de prueba inyectadas exitosamente.")
        print("\n=== ¡ÉXITO! Módulo SIM'S listo y verificado para demostración. ===")

if __name__ == '__main__':
    seed_sims()
