"""migrate_floats_to_decimal

Revision ID: f9a8b7c6d5e4
Revises: e00613d1d525
Create Date: 2026-08-01 20:55:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'f9a8b7c6d5e4'
down_revision = '92a1f2d6560b'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Forward migration for PostgreSQL / Supabase
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        columns = [
            ("settings", "tax_rate", "NUMERIC(5,4)"),
            ("tax", "rate", "NUMERIC(5,4)"),
            ("client", "credit_limit", "NUMERIC(12,2)"),
            ("product", "price", "NUMERIC(12,2)"),
            ("product", "price_bulk", "NUMERIC(12,2)"),
            ("product", "price_retail", "NUMERIC(12,2)"),
            ("product", "cost_price", "NUMERIC(12,2)"),
            ("sale", "total_amount", "NUMERIC(12,2)"),
            ("sale", "amount_paid", "NUMERIC(12,2)"),
            ("saleitem", "unit_price", "NUMERIC(12,2)"),
            ("saleitem", "total", "NUMERIC(12,2)"),
            ("saleitem", "cost_price_at_sale", "NUMERIC(12,2)"),
            ("payment", "amount", "NUMERIC(12,2)"),
            ("accountreceivable", "total", "NUMERIC(12,2)"),
            ("accountreceivable", "paid", "NUMERIC(12,2)"),
            ("accountreceivable", "balance", "NUMERIC(12,2)"),
            ("paymentallocation", "amount", "NUMERIC(12,2)"),
            ("cashbook", "total_amount", "NUMERIC(12,2)"),
            ("purchaseitem", "unit_cost", "NUMERIC(12,2)"),
            ("purchaseitem", "total", "NUMERIC(12,2)"),
            ("cashmovement", "amount", "NUMERIC(12,2)"),
        ]
        for table, col, new_type in columns:
            op.execute(f"ALTER TABLE {table} ALTER COLUMN {col} TYPE {new_type} USING {col}::{new_type.lower()}")

def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        columns = [
            ("settings", "tax_rate", "DOUBLE PRECISION"),
            ("tax", "rate", "DOUBLE PRECISION"),
            ("client", "credit_limit", "DOUBLE PRECISION"),
            ("product", "price", "DOUBLE PRECISION"),
            ("product", "price_bulk", "DOUBLE PRECISION"),
            ("product", "price_retail", "DOUBLE PRECISION"),
            ("product", "cost_price", "DOUBLE PRECISION"),
            ("sale", "total_amount", "DOUBLE PRECISION"),
            ("sale", "amount_paid", "DOUBLE PRECISION"),
            ("saleitem", "unit_price", "DOUBLE PRECISION"),
            ("saleitem", "total", "DOUBLE PRECISION"),
            ("saleitem", "cost_price_at_sale", "DOUBLE PRECISION"),
            ("payment", "amount", "DOUBLE PRECISION"),
            ("accountreceivable", "total", "DOUBLE PRECISION"),
            ("accountreceivable", "paid", "DOUBLE PRECISION"),
            ("accountreceivable", "balance", "DOUBLE PRECISION"),
            ("paymentallocation", "amount", "DOUBLE PRECISION"),
            ("cashbook", "total_amount", "DOUBLE PRECISION"),
            ("purchaseitem", "unit_cost", "DOUBLE PRECISION"),
            ("purchaseitem", "total", "DOUBLE PRECISION"),
            ("cashmovement", "amount", "DOUBLE PRECISION"),
        ]
        for table, col, new_type in columns:
            op.execute(f"ALTER TABLE {table} ALTER COLUMN {col} TYPE {new_type} USING {col}::{new_type.lower()}")
