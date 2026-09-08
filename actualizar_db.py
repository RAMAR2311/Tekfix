from app import create_app
from models import db
from sqlalchemy import text, inspect

app = create_app()
with app.app_context():
    print("Actualizando base de datos...")
    try:
        inspector = inspect(db.engine)
        
        # Columnas para arqueo_caja
        arqueo_cols = [c['name'] for c in inspector.get_columns('arqueo_caja')]
        with db.engine.connect() as conn:
            if 'efectivo_fisico' not in arqueo_cols:
                conn.execute(text("ALTER TABLE arqueo_caja ADD COLUMN efectivo_fisico NUMERIC(10, 2) DEFAULT 0.0;"))
            if 'diferencia' not in arqueo_cols:
                conn.execute(text("ALTER TABLE arqueo_caja ADD COLUMN diferencia NUMERIC(10, 2) DEFAULT 0.0;"))
            if 'observacion_diferencia' not in arqueo_cols:
                conn.execute(text("ALTER TABLE arqueo_caja ADD COLUMN observacion_diferencia VARCHAR(500);"))
            
            # Columnas para sim_cards
            sim_cols = [c['name'] for c in inspector.get_columns('sim_cards')]
            if 'sale_id' not in sim_cols:
                conn.execute(text("ALTER TABLE sim_cards ADD COLUMN sale_id INTEGER;"))
            
            # Columnas para products
            prod_cols = [c['name'] for c in inspector.get_columns('products')]
            if 'activo' not in prod_cols:
                conn.execute(text("ALTER TABLE products ADD COLUMN activo BOOLEAN DEFAULT 1;"))
            
            conn.commit()
        print("[OK] Columnas añadidas/verificadas exitosamente en 'arqueo_caja', 'sim_cards' y 'products'.")
    except Exception as e:
        print(f"Error al actualizar la base de datos: {e}")
