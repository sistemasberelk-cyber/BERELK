import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.dialects import postgresql
from sqlalchemy import create_engine
import importlib.util

def test_alembic_postgres_upgrade_statements():
    """Verifica que upgrade() ejecute sentencias ALTER TABLE válidas sobre dialecto PostgreSQL."""
    spec = importlib.util.spec_from_file_location("migration", "alembic/versions/f9a8b7c6d5e4_migrate_floats_to_decimal.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    executed_sqls = []

    class MockPgConnection:
        dialect = postgresql.dialect()
        def execute(self, sql):
            executed_sqls.append(str(sql))

    mock_conn = MockPgConnection()
    ctx = MigrationContext.configure(dialect_name="postgresql")
    op = Operations(ctx)

    # Monkeypatch op.get_bind y op.execute
    mod.op.get_bind = lambda: mock_conn
    mod.op.execute = lambda sql: executed_sqls.append(str(sql))

    mod.upgrade()

    print(f"\n[SE EJECUTARON {len(executed_sqls)} SENTENCIAS SQL DE MIGRACIÓN SOBRE POSTGRESQL]:")
    for sql in executed_sqls:
        print(f"  -> {sql}")
        assert "ALTER TABLE" in sql
        assert "TYPE NUMERIC" in sql
        assert "USING" in sql

    assert len(executed_sqls) == 21
