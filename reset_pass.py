from app import create_app
from models import db, User
from werkzeug.security import generate_password_hash

app = create_app()
with app.app_context():
    print("--- LISTADO DE USUARIOS ---")
    users = User.query.all()
    for u in users:
        print(f"Nombre: {u.nombre} | Email: {u.email} | Rol: {u.rol}")
    
    print("\n--- RESETEANDO CONTRASEÑA DE VENDEDOR ---")
    vendedor = User.query.filter_by(email='vendedor@tekfix.com').first()
    if vendedor:
        vendedor.password_hash = generate_password_hash('Tekfix1234')
        db.session.commit()
        print(f"Contraseña de '{vendedor.email}' reseteada a: Tekfix1234")
    else:
        print("ERROR: No se encontró al usuario vendedor@tekfix.com")
