import os
from flask import Flask, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, current_user
from flask_wtf.csrf import CSRFProtect

from dotenv import load_dotenv
load_dotenv()

# Importar la instancia de db desde models
from models import db, User

def get_database_uri():
    db_uri = os.environ.get('DATABASE_URL')
    if db_uri:
        return db_uri
    
    # Si no se configuró DATABASE_URL, verificar si PostgreSQL local está activo
    pg_uri = 'postgresql://postgres:admin123@localhost:5432/Tekfix'
    try:
        import socket
        with socket.create_connection(('localhost', 5432), timeout=0.8):
            return pg_uri
    except (OSError, socket.error):
        print("[INFO] PostgreSQL no está activo en localhost:5432. Usando SQLite local ('sqlite:///tekfix.db').")
        return 'sqlite:///tekfix.db'

def create_app():
    app = Flask(__name__)
    
    # Configuración mediante variables de entorno (con fallback dinámico)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-super-secreta')
    app.config['SQLALCHEMY_DATABASE_URI'] = get_database_uri()
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['UPLOAD_FOLDER'] = 'static/uploads'
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # Permitir hasta 16MB por archivo

    # Inicializar Extensiones
    db.init_app(app)
    Migrate(app, db)
    csrf = CSRFProtect(app)
    
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
    from routes.providers import providers_bp
    from routes.warranties import warranties_bp
    from routes.sims import sims_bp
    from routes.servidor import servidor_bp, calcular_info_pago_servidor
    
    app.register_blueprint(sales_bp, url_prefix='/sales')
    app.register_blueprint(inventory_bp, url_prefix='/inventory')
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(arqueo_bp, url_prefix='/arqueo')
    app.register_blueprint(gastos_bp, url_prefix='/gastos')
    app.register_blueprint(providers_bp, url_prefix='/providers')
    app.register_blueprint(warranties_bp, url_prefix='/garantias')
    app.register_blueprint(sims_bp, url_prefix='/sims')
    app.register_blueprint(servidor_bp, url_prefix='/servidor')
    csrf.exempt(servidor_bp)

    # Inyector de Contexto Global: Pago de Mensualidad del Servidor Zenic
    @app.context_processor
    def inject_pago_servidor():
        return {'pago_servidor': calcular_info_pago_servidor(app)}
    
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

    @app.route('/sw.js')
    @app.route('/service-worker.js')
    def service_worker():
        response = app.send_static_file('sw.js')
        response.headers['Service-Worker-Allowed'] = '/'
        response.headers['Cache-Control'] = 'no-cache'
        return response

    @app.route('/manifest.json')
    def manifest():
        return app.send_static_file('manifest.json')

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
            print("[INFO] Usuario maestro 'admin@tekfix.com' fue creado exitosamente.")
            
    app.run(debug=True)
