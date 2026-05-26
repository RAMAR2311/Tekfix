import os
from app import create_app
from models import db, User, Product, Sale, SalePayment, SaleDetail, Loss, Warranty, obtener_hora_bogota
from datetime import datetime, timedelta
from decimal import Decimal

def seed_monthly_data():
    app = create_app()
    with app.app_context():
        print("=== INICIANDO INYECCIÓN DE DATOS MENSUALES PARA PRUEBA ===")
        
        # 1. Obtener usuario para asociar las operaciones
        vendedor = User.query.filter_by(rol='vendedor').first() or User.query.first()
        admin = User.query.filter_by(rol='admin').first() or User.query.first()
        
        if not vendedor:
            print("ERROR: No se encontró ningún usuario para registrar ventas. Ejecuta la aplicación primero para crear el admin.")
            return

        print(f"Usando vendedor: {vendedor.nombre} (ID: {vendedor.id})")
        print(f"Usando admin: {admin.nombre} (ID: {admin.id})")

        # 2. Obtener o crear un producto demo
        product = Product.query.filter_by(sku='DEMO-FUNDA-01').first()
        if not product:
            product = Product(
                nombre='Funda Protectora Demo',
                sku='DEMO-FUNDA-01',
                tipo_inventario='tienda',
                cantidad_stock=100,
                precio_costo=Decimal("5000.00"),
                precio_minimo=Decimal("15000.00"),
                precio_sugerido=Decimal("20000.00"),
                observacion='Producto demo inyectado para pruebas del selector de mes'
            )
            db.session.add(product)
            db.session.flush()
            print("Creado producto demo 'DEMO-FUNDA-01'")
        else:
            print(f"Usando producto demo existente: {product.nombre}")

        # 3. Establecer fechas clave (Mes actual y Mes pasado)
        hoy = obtener_hora_bogota()
        mes_actual_dt = hoy.replace(day=10, hour=12, minute=0, second=0, microsecond=0)
        
        # Calcular mes pasado
        primer_dia_mes = hoy.replace(day=1)
        ultimo_dia_mes_pasado = primer_dia_mes - timedelta(days=1)
        mes_pasado_dt = ultimo_dia_mes_pasado.replace(day=15, hour=14, minute=30, second=0, microsecond=0)

        print(f"Fechas de inyección:\n - Mes Actual: {mes_actual_dt.strftime('%Y-%m-%d')}\n - Mes Pasado: {mes_pasado_dt.strftime('%Y-%m-%d')}")

        # 4. Limpiar datos de prueba anteriores con SKU 'DEMO-FUNDA-01' para evitar desbordamiento redundante
        detalles_antiguos = SaleDetail.query.filter_by(product_id=product.id).all()
        for d in detalles_antiguos:
            # Eliminar pagos y ventas asociadas a este detalle de prueba
            venta_asoc = d.venta
            if venta_asoc:
                SalePayment.query.filter_by(sale_id=venta_asoc.id).delete()
                Warranty.query.filter_by(sale_id=venta_asoc.id).delete()
                db.session.delete(venta_asoc)
            db.session.delete(d)
        
        Loss.query.filter_by(product_id=product.id).delete()
        Warranty.query.filter_by(product_id=product.id).delete()
        db.session.commit()
        print("Limpieza de datos de prueba previos con 'DEMO-FUNDA-01' completada.")

        # --- A. INYECTAR DATOS DEL MES ACTUAL ---
        # 1 Venta por $150.000
        venta_actual = Sale(
            vendedor_id=vendedor.id,
            monto_total=Decimal("150000.00"),
            metodo_pago='efectivo',
            fecha_venta=mes_actual_dt
        )
        db.session.add(venta_actual)
        db.session.flush()

        pago_actual = SalePayment(
            sale_id=venta_actual.id,
            metodo_pago='efectivo',
            monto=Decimal("150000.00")
        )
        db.session.add(pago_actual)

        detalle_actual = SaleDetail(
            sale_id=venta_actual.id,
            product_id=product.id,
            cantidad_vendida=5,
            precio_venta_final=Decimal("30000.00")
        )
        db.session.add(detalle_actual)

        # 1 Pérdida por $15.000 (3 unidades * $5.000 costo)
        perdida_actual = Loss(
            product_id=product.id,
            user_id=admin.id,
            quantity=3,
            cost_at_loss=Decimal("5000.00"),
            reason='Merma Demo - Mes Actual',
            date=mes_actual_dt
        )
        db.session.add(perdida_actual)

        # 1 Garantía en el mes actual
        garantia_actual = Warranty(
            sale_id=venta_actual.id,
            product_id=product.id,
            quantity=1,
            reason='Falla de botón (Demo Mes Actual)',
            resolution='Pendiente',
            created_at=mes_actual_dt
        )
        db.session.add(garantia_actual)
        
        print("[OK] Datos del Mes Actual inyectados ($150.000 ventas, $15.000 pérdidas, 1 garantía).")


        # --- B. INYECTAR DATOS DEL MES PASADO ---
        # 1 Venta por $280.000
        venta_pasado = Sale(
            vendedor_id=vendedor.id,
            monto_total=Decimal("280000.00"),
            metodo_pago='transferencia',
            fecha_venta=mes_pasado_dt
        )
        db.session.add(venta_pasado)
        db.session.flush()

        pago_pasado = SalePayment(
            sale_id=venta_pasado.id,
            metodo_pago='nequi',
            monto=Decimal("280000.00")
        )
        db.session.add(pago_pasado)

        detalle_pasado = SaleDetail(
            sale_id=venta_pasado.id,
            product_id=product.id,
            cantidad_vendida=7,
            precio_venta_final=Decimal("40000.00")
        )
        db.session.add(detalle_pasado)

        # 1 Pérdida por $8.000 (2 unidades * $4.000 costo de ejemplo)
        perdida_pasada = Loss(
            product_id=product.id,
            user_id=admin.id,
            quantity=2,
            cost_at_loss=Decimal("4000.00"),
            reason='Merma Demo - Mes Pasado',
            date=mes_pasado_dt
        )
        db.session.add(perdida_pasada)

        # 3 Garantías en el mes pasado
        for i in range(1, 4):
            garantia_pasada = Warranty(
                sale_id=venta_pasado.id,
                product_id=product.id,
                quantity=1,
                reason=f'Defecto de pantalla demo #{i} (Mes Pasado)',
                resolution='Pendiente',
                created_at=mes_pasado_dt + timedelta(hours=i)
            )
            db.session.add(garantia_pasada)
            
        print("[OK] Datos del Mes Pasado inyectados ($280.000 ventas, $8.000 pérdidas, 3 garantías).")

        db.session.commit()
        print("\n=== ¡ÉXITO! Datos de prueba inyectados de forma perfecta. ===")

if __name__ == '__main__':
    seed_monthly_data()
