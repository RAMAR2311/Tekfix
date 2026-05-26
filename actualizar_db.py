from app import create_app
from models import db
from sqlalchemy import text

app = create_app()
with app.app_context():
    print("Actualizando base de datos...")
    try:
        # Agregar columnas a la tabla arqueo_caja y sim_cards
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE arqueo_caja ADD COLUMN IF NOT EXISTS efectivo_fisico NUMERIC(10, 2) DEFAULT 0.0;"))
            conn.execute(text("ALTER TABLE arqueo_caja ADD COLUMN IF NOT EXISTS diferencia NUMERIC(10, 2) DEFAULT 0.0;"))
            conn.execute(text("ALTER TABLE arqueo_caja ADD COLUMN IF NOT EXISTS observacion_diferencia VARCHAR(500);"))
            conn.execute(text("ALTER TABLE sim_cards ADD COLUMN IF NOT EXISTS sale_id INTEGER REFERENCES sales(id) ON DELETE SET NULL;"))
            conn.commit()
        print("[OK] Columnas añadidas exitosamente a 'arqueo_caja' y 'sim_cards'.")
    except Exception as e:
        print(f"Error al actualizar la base de datos: {e}")
