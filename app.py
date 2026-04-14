import os
from flask import Flask, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, current_user
from flask_wtf.csrf import CSRFProtect

# Importar la instancia de db desde models
from models import db, User

def create_app():
    app = Flask(__name__)
    
    # Configuración mediante variables de entorno (con fallback a PostgreSQL local)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-super-secreta')
    
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'postgresql://postgres:admin123@localhost:5432/Tekfix')
    
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['UPLOAD_FOLDER'] = 'static/uploads'

    # Inicializar Extensiones
    db.init_app(app)
    Migrate(app, db)
    CSRFProtect(app)
    
    login_manager = LoginManager()
    login_manager.login_view = 'auth_bp.login'
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Importar y Registrar Blueprints
    from routes.sales import sales_bp
    from routes.inventory import inventory_bp
    from routes.auth import auth_bp
    from routes.arqueo import arqueo_bp
    from routes.gastos import gastos_bp
    
    app.register_blueprint(sales_bp, url_prefix='/sales')
    app.register_blueprint(inventory_bp, url_prefix='/inventory')
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(arqueo_bp, url_prefix='/arqueo')
    app.register_blueprint(gastos_bp, url_prefix='/gastos')
    
    # Registro de Blueprint Admin
    from routes.admin import admin_bp
    app.register_blueprint(admin_bp, url_prefix='/admin')

    # Registro de Blueprint Bodega
    from routes.bodega import bodega_bp
    app.register_blueprint(bodega_bp, url_prefix='/bodega')

    @app.template_filter('cop')
    def cop_filter(value):
        if value is None:
            return "0"
        try:
            # Formateo a moneda colombiana (sin decimales, separador de miles con punto)
            return "{:,.0f}".format(float(value)).replace(',', '.')
        except (ValueError, TypeError):
            return value

    @app.route('/')
    def index():
        # Redirección de sesión y rol de usuario
        if not current_user.is_authenticated:
            return redirect(url_for('auth_bp.login'))
            
        if current_user.rol == 'admin':
            return redirect(url_for('admin_bp.dashboard'))
            
        if current_user.rol == 'bodega':
            return redirect(url_for('bodega_bp.dashboard'))
            
        # Por defecto, Vendedores van directo a Cajas
        return redirect(url_for('sales_bp.procesar_venta'))

    return app

if __name__ == '__main__':
    app = create_app()
    
    # ---------------- LÓGICA DE INICIALIZACIÓN ----------------
    with app.app_context():
        from models import db, User
        from werkzeug.security import generate_password_hash
        
        # Aseguramos que las tablas existan sin romper migraciones
        db.create_all()
        
        # Crear la carpeta de imágenes si no existe
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        
        # Verificamos e instanciamos al Administrador si no existe
        if not User.query.filter_by(email='admin@tekfix.com').first():
            master_admin = User(
                nombre='Gestión Administrador',
                email='admin@tekfix.com',
                password_hash=generate_password_hash('Admin123'),
                rol='admin' # Rol dictaminado por los requerimientos
            )
            db.session.add(master_admin)
            db.session.commit()
            print("🚀 [INFO] Usuario maestro 'admin@tekfix.com' fue creado automáticamente.")
            
    app.run(debug=True)
