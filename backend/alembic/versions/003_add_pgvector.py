"""Add pgvector embeddings and reference clause corpus

Revision ID: 003_add_pgvector
Revises: 002_add_clause_explanations
Create Date: 2026-10-01 00:00:00.000000

Requires the `vector` extension to be available on the server (on Azure
Database for PostgreSQL it must be allow-listed via azure.extensions first).

Index parameters are fixed here on purpose so the schema is deterministic;
the benchmark harness rebuilds indexes with other parameters and restores
these defaults afterwards.
"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision = '003_add_pgvector'
down_revision = '002_add_clause_explanations'
branch_labels = None
depends_on = None

EMBEDDING_DIM = 384


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Contract clauses: exact search scoped by document_id, so a b-tree on
    # document_id instead of an ANN index on the embedding.
    op.add_column('clauses', sa.Column('embedding', Vector(EMBEDDING_DIM), nullable=True))
    op.create_index('ix_clauses_document_id', 'clauses', ['document_id'], unique=False)

    # Precedent corpus
    op.create_table(
        'reference_clauses',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source_contract', sa.String(length=512), nullable=False),
        sa.Column('category', sa.String(length=100), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('embedding', Vector(EMBEDDING_DIM), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_reference_clauses_category', 'reference_clauses', ['category'], unique=False)
    op.execute(
        "CREATE INDEX ix_reference_clauses_embedding_hnsw ON reference_clauses "
        "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_reference_clauses_embedding_hnsw")
    op.drop_index('ix_reference_clauses_category', table_name='reference_clauses')
    op.drop_table('reference_clauses')
    op.drop_index('ix_clauses_document_id', table_name='clauses')
    op.drop_column('clauses', 'embedding')
    # The extension is intentionally left installed: it may pre-date this
    # migration (e.g. created by a server admin) and other objects may use it.
