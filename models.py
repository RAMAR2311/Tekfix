from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
import pytz

db = SQLAlchemy()

def obtener_hora_bogota():
    """Inyecta el uso de red horario en Colombia a nivel de sistema operativo."""
    return datetime.now(pytz.timezone('America/Bogota')).replace(tzinfo=None)

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    telefono = db.Column(db.String(20)) # Nuevo Campo de Contacto (Nullable por Defecto)
    password_hash = db.Column(db.String(256), nullable=False)
    rol = db.Column(db.String(50), nullable=False, default='vendedor')
    
    ventas = db.relationship('Sale', backref='vendedor', lazy=True)
    ajustes_stock = db.relationship('StockAdjustment', backref='admin', lazy=True)
    arqueos = db.relationship('ArqueoCaja', backref='cajero', lazy=True)

class Product(db.Model):
    __tablename__ = 'products'
    
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False)
    sku = db.Column(db.String(50), unique=True, nullable=False, index=True)
    tipo_inventario = db.Column(db.String(50), nullable=False, server_default='tienda') # 'tienda' o 'bodega'
    cantidad_stock = db.Column(db.Integer, nullable=False, default=0)
    precio_costo = db.Column(db.Numeric(10, 2), nullable=False, default=0.00) # El Costo de Bodega
    precio_minimo = db.Column(db.Numeric(10, 2), nullable=False)
    precio_sugerido = db.Column(db.Numeric(10, 2), nullable=False)
    imagen = db.Column(db.String(255), nullable=True) # Nombre de la foto subida
    observacion = db.Column(db.Text, nullable=True) # Nota descriptiva
    fecha_creacion = db.Column(db.DateTime, default=obtener_hora_bogota)
    
    detalles_venta = db.relationship('SaleDetail', backref='producto', lazy=True)
    ajustes_stock = db.relationship('StockAdjustment', backref='producto_rel', lazy=True)
    variantes = db.relationship('ProductVariant', backref='producto', lazy=True, cascade="all, delete-orphan")

    @property
    def total_stock(self):
        if self.variantes:
            return sum(v.cantidad_stock for v in self.variantes)
        return self.cantidad_stock

    @property
    def rango_precios(self):
        if not self.variantes:
            return None
        precios = [v.precio_sugerido for v in self.variantes]
        if not precios:
            return None
        min_p = min(precios)
        max_p = max(precios)
        if min_p == max_p:
            return min_p
        return (min_p, max_p)

class ProductVariant(db.Model):
    __tablename__ = 'product_variants'

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    nombre_variante = db.Column(db.String(100), nullable=False)
    cantidad_stock = db.Column(db.Integer, nullable=False, default=0)
    
    # Nuevos precios específicos para variantes
    precio_costo = db.Column(db.Numeric(10, 2), nullable=True) 
    precio_minimo = db.Column(db.Numeric(10, 2), nullable=True)
    precio_sugerido = db.Column(db.Numeric(10, 2), nullable=True)

class Loss(db.Model):
    __tablename__ = 'losses'
    
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    cost_at_loss = db.Column(db.Numeric(10, 2), nullable=False)
    reason = db.Column(db.String(255), nullable=True)
    date = db.Column(db.DateTime, default=obtener_hora_bogota)
    
    producto = db.relationship('Product', backref='perdidas', lazy=True)

class Sale(db.Model):
    __tablename__ = 'sales'
    
    id = db.Column(db.Integer, primary_key=True)
    vendedor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    fecha_venta = db.Column(db.DateTime, default=obtener_hora_bogota)
    monto_total = db.Column(db.Numeric(10, 2), nullable=False, default=0.0)
    metodo_pago = db.Column(db.String(50), nullable=False, default='efectivo')
    
    detalles = db.relationship('SaleDetail', backref='venta', lazy=True, cascade="all, delete-orphan")
    pagos = db.relationship('SalePayment', backref='venta', lazy=True, cascade="all, delete-orphan")

    @property
    def metodo_pago_display(self):
        """Retorna un resumen legible del método de pago.
        Si es pago único, retorna el nombre del método.
        Si es mixto, retorna 'Pago Mixto' con desglose."""
        if not self.pagos:
            # Retrocompatibilidad con ventas antiguas que solo tienen metodo_pago
            return self.metodo_pago.capitalize() if self.metodo_pago else 'Efectivo'
        if len(self.pagos) == 1:
            return self.pagos[0].metodo_pago.capitalize()
        return 'Pago Mixto'

class SalePayment(db.Model):
    """Modelo para soportar pagos mixtos/parciales por venta.
    Permite registrar múltiples métodos de pago en una sola venta.
    Ej: $50.000 en efectivo + $30.000 por Nequi = $80.000 total."""
    __tablename__ = 'sale_payments'

    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'), nullable=False)
    metodo_pago = db.Column(db.String(50), nullable=False)  # efectivo, nequi, bancolombia, daviplata
    monto = db.Column(db.Numeric(10, 2), nullable=False)

class SaleDetail(db.Model):
    __tablename__ = 'sale_details'
    
    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=True)
    variant_id = db.Column(db.Integer, db.ForeignKey('product_variants.id'), nullable=True)
    cantidad_vendida = db.Column(db.Integer, nullable=False)
    precio_venta_final = db.Column(db.Numeric(10, 2), nullable=False)
    # Campos para productos manuales (prestados de otros locales)
    nombre_manual = db.Column(db.String(200), nullable=True)
    precio_costo_manual = db.Column(db.Numeric(10, 2), nullable=True)

    variante = db.relationship('ProductVariant', backref='ventas_rel', lazy=True)

class StockAdjustment(db.Model):
    __tablename__ = 'stock_adjustments'
    
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    admin_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    tipo_movimiento = db.Column(db.String(100), nullable=True) # Ej: Creación Inicial, Ajuste Manual
    stock_anterior = db.Column(db.Integer, nullable=False)
    stock_nuevo = db.Column(db.Integer, nullable=False)
    fecha_ajuste = db.Column(db.DateTime, default=obtener_hora_bogota)

class ArqueoCaja(db.Model):
    __tablename__ = 'arqueo_caja'
    
    id = db.Column(db.Integer, primary_key=True)
    vendedor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    fecha_arqueo = db.Column(db.Date, nullable=False)
    base_inicial = db.Column(db.Numeric(10, 2), nullable=False, default=0.0)
    gastos_del_dia = db.Column(db.Numeric(10, 2), nullable=False, default=0.0)
    observaciones_gastos = db.Column(db.String(255), nullable=True)
    total_efectivo_sistema = db.Column(db.Numeric(10, 2), nullable=False, default=0.0)
    total_transferencia_sistema = db.Column(db.Numeric(10, 2), nullable=False, default=0.0)
    fecha_creacion = db.Column(db.DateTime, default=obtener_hora_bogota)

class Maneo(db.Model):
    __tablename__ = 'maneos'

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    variant_id = db.Column(db.Integer, db.ForeignKey('product_variants.id'), nullable=True)
    local_vecino = db.Column(db.String(150), nullable=False)
    cantidad = db.Column(db.Integer, nullable=False)
    estado = db.Column(db.String(50), nullable=False, default='PENDIENTE') # PENDIENTE, FACTURADO, DEVUELTO
    fecha_prestamo = db.Column(db.DateTime, default=obtener_hora_bogota)
    fecha_resolucion = db.Column(db.DateTime, nullable=True)

    producto = db.relationship('Product', backref='maneos', lazy=True)
    variante = db.relationship('ProductVariant', backref='maneos_rel', lazy=True)

class Expense(db.Model):
    __tablename__ = 'expenses'
    
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    tipo_gasto = db.Column(db.String(50), nullable=False) # 'Gasto Diario' o 'Costo Indirecto'
    categoria = db.Column(db.String(100), nullable=False)
    descripcion = db.Column(db.String(255), nullable=True)
    monto = db.Column(db.Numeric(10, 2), nullable=False)
    fecha_gasto = db.Column(db.DateTime, default=obtener_hora_bogota)

    usuario = db.relationship('User', backref='gastos', lazy=True)

class Cliente(db.Model):
    __tablename__ = 'clientes'

    id = db.Column(db.Integer, primary_key=True)
    nombre_o_razon_social = db.Column(db.String(150), nullable=False)
    documento_o_nit = db.Column(db.String(50), unique=True, nullable=False, index=True)
    telefono = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(120), nullable=True)
    direccion = db.Column(db.String(255), nullable=True)
    fecha_registro = db.Column(db.DateTime, default=obtener_hora_bogota)

    facturas = db.relationship('FacturaBodega', backref='cliente', lazy=True)

    @property
    def deuda_total(self):
        return sum(f.saldo_pendiente for f in self.facturas)

    @property
    def estado_global(self):
        return "Con Deuda" if self.deuda_total > 0 else "Al Día"

class FacturaBodega(db.Model):
    __tablename__ = 'facturas_bodega'

    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    numero_factura = db.Column(db.String(100), nullable=False)
    archivo_ruta = db.Column(db.String(255), nullable=False)
    monto_total = db.Column(db.Numeric(10, 2), nullable=False, default=0.0)
    estado = db.Column(db.String(50), nullable=False, default='Pendiente') # Pendiente, Parcial, Pagado
    fecha_subida = db.Column(db.DateTime, default=obtener_hora_bogota)

    usuario = db.relationship('User', backref='facturas_subidas', lazy=True)
    abonos = db.relationship('AbonoBodega', backref='factura', lazy=True, cascade="all, delete-orphan")
    detalles = db.relationship('FacturaBodegaDetalle', backref='factura', lazy=True, cascade="all, delete-orphan")

    @property
    def saldo_pendiente(self):
        total_abonado = sum(abono.monto for abono in self.abonos)
        return float(self.monto_total) - float(total_abonado)

class FacturaBodegaDetalle(db.Model):
    __tablename__ = 'facturas_bodega_detalles'

    id = db.Column(db.Integer, primary_key=True)
    factura_id = db.Column(db.Integer, db.ForeignKey('facturas_bodega.id'), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    cantidad = db.Column(db.Integer, nullable=False)
    precio_venta = db.Column(db.Numeric(10, 2), nullable=True) # Opcional para futuros análisis

    producto = db.relationship('Product', backref='detalles_factura_bodega', lazy=True)

class AbonoBodega(db.Model):
    __tablename__ = 'abonos_bodega'

    id = db.Column(db.Integer, primary_key=True)
    factura_id = db.Column(db.Integer, db.ForeignKey('facturas_bodega.id'), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    monto = db.Column(db.Numeric(10, 2), nullable=False)
    metodo_pago = db.Column(db.String(50), nullable=False, default='efectivo')
    observacion = db.Column(db.String(255), nullable=True)
    fecha_abono = db.Column(db.DateTime, default=obtener_hora_bogota)

    usuario = db.relationship('User', backref='abonos_registrados', lazy=True)
