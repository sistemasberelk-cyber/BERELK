"""
Backup manual pre-migración — NexPOS SaaS
Exporta a JSON todas las filas de las tablas que la migración de Decimal va a alterar.
No requiere pg_dump instalado: usa SQLAlchemy (ya es dependencia del proyecto).

USO:
1. Copiá este archivo a la raíz de tu proyecto NexPOS SaaS (junto a alembic.ini).
2. Seteá la variable de entorno DATABASE_URL apuntando a STAGING (con la contraseña nueva).
   Windows (PowerShell):  $env:DATABASE_URL="postgresql://usuario:PASSWORD@host:puerto/postgres"
   Mac/Linux:             export DATABASE_URL="postgresql://usuario:PASSWORD@host:puerto/postgres"
3. Corré: python backup_pre_migracion.py
4. Va a crear una carpeta ./backup_pre_migracion_<timestamp>/ con un .json por tabla.

Esto NO reemplaza un backup completo de infraestructura, pero cubre exactamente
las tablas/columnas que la migración a Decimal va a tocar, para poder restaurar
los datos manualmente si algo sale mal.
"""

import os
import sys
import json
from datetime import datetime, date
from decimal import Decimal

try:
    from sqlalchemy import create_engine, text
except ImportError:
    print("ERROR: falta SQLAlchemy. Si el proyecto ya lo usa (Alembic), corré esto")
    print("       desde el mismo entorno virtual / carpeta del proyecto.")
    sys.exit(1)

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: no está seteada la variable de entorno DATABASE_URL.")
    print("Seteala apuntando a STAGING antes de correr este script.")
    sys.exit(1)

# Tablas afectadas por la migración de float -> Decimal (ver inventario de la sesión)
TABLES_TO_BACKUP = [
    "settings",
    "tax",
    "client",
    "product",
    "sale",
    "saleitem",
    "payment",
    "accountreceivable",
    "paymentallocation",
    "cashbook",
    "purchaseitem",
    "cashmovement",
]


def json_default(obj):
    """Convierte tipos no serializables (Decimal, datetime, date) a JSON-friendly."""
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    return str(obj)


def main():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = f"./backup_pre_migracion_{timestamp}"
    os.makedirs(out_dir, exist_ok=True)

    print(f"Conectando a la base de datos...")
    engine = create_engine(DATABASE_URL)

    resumen = {}

    with engine.connect() as conn:
        for table in TABLES_TO_BACKUP:
            try:
                result = conn.execute(text(f"SELECT * FROM {table}"))
                rows = [dict(row._mapping) for row in result]
            except Exception as e:
                print(f"  [AVISO] No se pudo leer la tabla '{table}': {e}")
                resumen[table] = f"ERROR: {e}"
                continue

            filepath = os.path.join(out_dir, f"{table}.json")
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(rows, f, default=json_default, indent=2, ensure_ascii=False)

            print(f"  OK  {table}: {len(rows)} filas -> {filepath}")
            resumen[table] = len(rows)

    # Guardar un resumen general
    with open(os.path.join(out_dir, "_resumen.json"), "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": timestamp,
            "tablas": resumen,
        }, f, indent=2, ensure_ascii=False)

    print(f"\nBackup completo en: {out_dir}/")
    print("Guardá esta carpeta en un lugar seguro (fuera del repo) antes de migrar.")


if __name__ == "__main__":
    main()
