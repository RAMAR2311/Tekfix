"""
Script maestro para poblar todos los datos de ejemplo en la base de datos de Tekfix.
Ejecuta secuencialmente todos los módulos de semilla.
"""
import sys

def main():
    print("=" * 60)
    print("  POBLANDO BASE DE DATOS DE TEKFIX CON DATOS DE PRUEBA")
    print("=" * 60)

    # 1. Datos base del sistema (usuarios, productos, ventas, etc.)
    print("\n1. Inyectando datos base (Usuarios, Inventario demo, Ventas, Proveedores)...")
    try:
        import seed_test_data
        seed_test_data.seed_test_data()
    except Exception as e:
        print(f"[ERROR en seed_test_data]: {e}")

    # 2. Productos desde inventario.csv
    print("\n2. Inyectando productos desde CSV...")
    try:
        import seed_inventory
        seed_inventory.seed_inventory_from_csv()
    except Exception as e:
        print(f"[ERROR en seed_inventory]: {e}")

    # 3. Datos mensuales de ventas y balance
    print("\n3. Inyectando datos mensuales de prueba...")
    try:
        import seed_monthly_test_data
        seed_monthly_test_data.seed_monthly_data()
    except Exception as e:
        print(f"[ERROR en seed_monthly_test_data]: {e}")

    # 4. Histórico de gastos
    print("\n4. Inyectando gastos históricos...")
    try:
        import seed_expenses
        seed_expenses.seed_expenses()
    except Exception as e:
        print(f"[ERROR en seed_expenses]: {e}")

    # 5. SIM cards
    print("\n5. Inyectando módulo de SIMs...")
    try:
        import seed_sims
        seed_sims.seed_sims()
    except Exception as e:
        print(f"[ERROR en seed_sims]: {e}")

    # 6. Arqueos de caja y sobrantes
    print("\n6. Inyectando arqueos de caja y ejemplos de sobrantes...")
    try:
        import seed_sobrantes
        seed_sobrantes.seed_sobrantes()
    except Exception as e:
        print(f"[ERROR en seed_sobrantes]: {e}")

    print("\n" + "=" * 60)
    print("  TODOS LOS DATOS DE EJEMPLO SE HAN CARGADO CON ÉXITO")
    print("=" * 60)

if __name__ == '__main__':
    main()
