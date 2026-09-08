from app import create_app
from models import db
from sqlalchemy import inspect

app = create_app()
with app.app_context():
    print("--- REVISANDO COLUMNAS REALES EN LA DB ---")
    try:
        inspector = inspect(db.engine)
        columnas = [col['name'] for col in inspector.get_columns('arqueo_caja')]
        print(f"Columnas encontradas en arqueo_caja: {columnas}")
        
        needed = ['efectivo_fisico', 'diferencia', 'observacion_diferencia']
        missing = [c for c in needed if c not in columnas]
        
        if not missing:
            print("¡TODO CORRECTO! Todas las columnas existen.")
        else:
            print(f"FALTAN: {missing}")
            
    except Exception as e:
        print(f"Error al consultar la DB: {e}")
