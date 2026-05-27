# pyright: reportCallIssue=false
from app import create_app
from models import db, User, Expense, obtener_hora_bogota
from decimal import Decimal
from datetime import datetime

def seed_expenses():
    app = create_app()
    with app.app_context():
        print("=== INICIALIZANDO SEMILLA HISTÓRICA DE GASTOS ===")
        
        # 1. Obtener un usuario para relacionar los gastos
        admin_user = User.query.filter_by(rol='admin').first()
        vendedor_user = User.query.filter_by(rol='vendedor').first()
        
        if not admin_user:
            admin_user = User.query.first()
            
        if not admin_user:
            print("[ERROR] No hay usuarios en la base de datos. Por favor, inicia la aplicación primero.")
            return
            
        admin_id = admin_user.id
        vendedor_id = vendedor_user.id if vendedor_user else admin_id
        
        # Limpiar gastos antiguos para tener un entorno limpio
        Expense.query.delete()
        db.session.commit()
        print("[OK] Limpieza de gastos antiguos completada.")
        
        # 2. Definir gastos realistas para cada mes
        # Formato de fechas: 2026-MM-DD
        data_gastos = [
            # ================= FEBRERO 2026 =================
            {
                'user_id': admin_id,
                'tipo': 'Costo Indirecto',
                'categoria': 'Arriendo',
                'monto': 1200000.00,
                'desc': 'Canon de arrendamiento local central - Febrero',
                'fecha': '2026-02-05 10:00:00'
            },
            {
                'user_id': admin_id,
                'tipo': 'Costo Indirecto',
                'categoria': 'Servicios Públicos',
                'monto': 290000.00,
                'desc': 'Servicio de energía y agua - Febrero',
                'fecha': '2026-02-12 15:30:00'
            },
            {
                'user_id': vendedor_id,
                'tipo': 'Gasto Diario',
                'categoria': 'Alimentación',
                'monto': 60000.00,
                'desc': 'Refrigerios del equipo',
                'fecha': '2026-02-18 16:45:00'
            },
            {
                'user_id': vendedor_id,
                'tipo': 'Gasto Diario',
                'categoria': 'Transporte / Fletes',
                'monto': 180000.00,
                'desc': 'Envío de mercancía tienda externa',
                'fecha': '2026-02-24 11:20:00'
            },
            
            # ================= MARZO 2026 =================
            {
                'user_id': admin_id,
                'tipo': 'Costo Indirecto',
                'categoria': 'Arriendo',
                'monto': 1200000.00,
                'desc': 'Canon de arrendamiento local central - Marzo',
                'fecha': '2026-03-05 09:30:00'
            },
            {
                'user_id': admin_id,
                'tipo': 'Costo Indirecto',
                'categoria': 'Servicios Públicos',
                'monto': 340000.00,
                'desc': 'Servicio de luz y acueducto - Marzo',
                'fecha': '2026-03-10 14:15:00'
            },
            {
                'user_id': admin_id,
                'tipo': 'Costo Indirecto',
                'categoria': 'Internet / Teléfono',
                'monto': 150000.00,
                'desc': 'Plan de fibra óptica Claro Empresas',
                'fecha': '2026-03-15 10:45:00'
            },
            {
                'user_id': vendedor_id,
                'tipo': 'Gasto Diario',
                'categoria': 'Alimentación',
                'monto': 95000.00,
                'desc': 'Almuerzo por reunión trimestral de ventas',
                'fecha': '2026-03-15 13:00:00'
            },
            {
                'user_id': admin_id,
                'tipo': 'Costo Indirecto',
                'categoria': 'Nómina',
                'monto': 500000.00,
                'desc': 'Comisiones adicionales sobre ventas - Marzo',
                'fecha': '2026-03-28 18:00:00'
            },
            {
                'user_id': vendedor_id,
                'tipo': 'Gasto Diario',
                'categoria': 'Aseo y Mantenimiento',
                'monto': 45000.00,
                'desc': 'Elementos de aseo y desinfectantes',
                'fecha': '2026-03-29 08:30:00'
            },
            
            # ================= ABRIL 2026 =================
            {
                'user_id': admin_id,
                'tipo': 'Costo Indirecto',
                'categoria': 'Arriendo',
                'monto': 1200000.00,
                'desc': 'Canon de arrendamiento local central - Abril',
                'fecha': '2026-04-05 11:00:00'
            },
            {
                'user_id': admin_id,
                'tipo': 'Costo Indirecto',
                'categoria': 'Servicios Públicos',
                'monto': 280000.00,
                'desc': 'Servicios públicos energía y agua - Abril',
                'fecha': '2026-04-11 16:00:00'
            },
            {
                'user_id': vendedor_id,
                'tipo': 'Gasto Diario',
                'categoria': 'Alimentación',
                'monto': 110000.00,
                'desc': 'Almuerzo equipo de soporte técnico',
                'fecha': '2026-04-15 13:15:00'
            },
            {
                'user_id': vendedor_id,
                'tipo': 'Gasto Diario',
                'categoria': 'Caja Menor',
                'monto': 80000.00,
                'desc': 'Repuestos menores de papelería y ganchos',
                'fecha': '2026-04-20 14:00:00'
            },
            {
                'user_id': vendedor_id,
                'tipo': 'Gasto Diario',
                'categoria': 'Insumos Varios',
                'monto': 45000.00,
                'desc': 'Tornillería y cintas doble cara para pantallas',
                'fecha': '2026-04-25 15:40:00'
            },
            
            # ================= MAYO 2026 (Mes Actual) =================
            {
                'user_id': admin_id,
                'tipo': 'Costo Indirecto',
                'categoria': 'Arriendo',
                'monto': 1200000.00,
                'desc': 'Canon de arrendamiento local central - Mayo',
                'fecha': '2026-05-05 10:30:00'
            },
            {
                'user_id': admin_id,
                'tipo': 'Costo Indirecto',
                'categoria': 'Servicios Públicos',
                'monto': 320000.00,
                'desc': 'Recibo de energía Codensa - Mayo',
                'fecha': '2026-05-09 14:50:00'
            },
            {
                'user_id': admin_id,
                'tipo': 'Costo Indirecto',
                'categoria': 'Internet / Teléfono',
                'monto': 150000.00,
                'desc': 'Internet fibra óptica local principal - Mayo',
                'fecha': '2026-05-12 11:15:00'
            },
            {
                'user_id': vendedor_id,
                'tipo': 'Gasto Diario',
                'categoria': 'Alimentación',
                'monto': 85000.00,
                'desc': 'Almuerzos día de alta afluencia de inventario',
                'fecha': '2026-05-18 13:10:00'
            },
            {
                'user_id': vendedor_id,
                'tipo': 'Gasto Diario',
                'categoria': 'Alimentación',
                'monto': 40000.00,
                'desc': 'Café y empanadas para los técnicos',
                'fecha': '2026-05-20 09:40:00'
            },
            {
                'user_id': vendedor_id,
                'tipo': 'Gasto Diario',
                'categoria': 'Aseo y Mantenimiento',
                'monto': 60000.00,
                'desc': 'Jabón líquido, bolsas de basura y aromatizantes',
                'fecha': '2026-05-24 16:30:00'
            }
        ]
        
        # 3. Registrar los gastos en la base de datos
        for g in data_gastos:
            fecha_obj = datetime.strptime(g['fecha'], '%Y-%m-%d %H:%M:%S')
            nuevo_gasto = Expense(
                usuario_id=g['user_id'],
                tipo_gasto=g['tipo'],
                categoria=g['categoria'],
                monto=Decimal(str(g['monto'])),
                descripcion=g['desc'],
                fecha_gasto=fecha_obj
            )
            db.session.add(nuevo_gasto)
            
        db.session.commit()
        print(f"[OK] {len(data_gastos)} registros de gastos históricos creados exitosamente.")
        print("\n=== ¡ÉXITO! Base de datos poblada de forma impecable con datos de Febrero a Mayo. ===")

if __name__ == '__main__':
    seed_expenses()
