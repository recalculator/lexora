"""Store all CUAD categories of a reference clause in one row

Revision ID: 004_reference_categories_array
Revises: 003_add_pgvector
Create Date: 2026-10-01 00:00:00.000000

Identical clause texts within a contract can carry several CUAD categories
(e.g. License Grant and Non-Transferable License). They are stored as one row
with a `categories` array instead of one row per category. Category filters
use array operators (&&, @>) backed by a GIN index.

Downgrade restores the single `category` column from the first array element
(lossy for multi-category rows).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '004_reference_categories_array'
down_revision = '003_add_pgvector'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('reference_clauses', sa.Column('categories', postgresql.ARRAY(sa.String(length=100)), nullable=True))
    op.execute("UPDATE reference_clauses SET categories = ARRAY[category]")
    op.alter_column('reference_clauses', 'categories', nullable=False)
    op.drop_index('ix_reference_clauses_category', table_name='reference_clauses')
    op.drop_column('reference_clauses', 'category')
    op.create_index(
        'ix_reference_clauses_categories', 'reference_clauses', ['categories'],
        unique=False, postgresql_using='gin',
    )


def downgrade() -> None:
    op.add_column('reference_clauses', sa.Column('category', sa.String(length=100), nullable=True))
    op.execute("UPDATE reference_clauses SET category = categories[1]")
    op.alter_column('reference_clauses', 'category', nullable=False)
    op.drop_index('ix_reference_clauses_categories', table_name='reference_clauses')
    op.drop_column('reference_clauses', 'categories')
    op.create_index('ix_reference_clauses_category', 'reference_clauses', ['category'], unique=False)
