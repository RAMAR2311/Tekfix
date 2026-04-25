from app import create_app
from models import db
from sqlalchemy import text

app = create_app()
with app.app_context():
    print("--- REVISANDO COLUMNAS REALES EN LA DB ---")
    try:
        res = db.session.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='arqueo_caja'")).fetchall()
        columnas = [r[0] for r in res]
        print(f"Columnas encontradas: {columnas}")
        
        needed = ['efectivo_fisico', 'diferencia', 'observacion_diferencia']
        missing = [c for c in needed if c not in columnas]
        
        if not missing:
            print("¡TODO CORRECTO! Todas las columnas existen.")
        else:
            print(f"FALTAN: {missing}")
            
    except Exception as e:
        print(f"Error al consultar la DB: {e}")
