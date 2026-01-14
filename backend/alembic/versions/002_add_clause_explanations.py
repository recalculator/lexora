"""Add clause explanations table

Revision ID: 002_add_clause_explanations
Revises: 001_initial
Create Date: 2024-01-13 16:55:00.000000

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime

# revision identifiers, used by Alembic.
revision = '002_add_clause_explanations'
down_revision = '001_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Clause explanations table
    op.create_table(
        'clause_explanations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=False),
        sa.Column('clause_idx', sa.Integer(), nullable=False),
        sa.Column('style', sa.String(length=20), nullable=False),
        sa.Column('json_output', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_clause_explanations_id'), 'clause_explanations', ['id'], unique=False)
    # Add index for faster lookups
    op.create_index('ix_clause_explanations_doc_clause_style', 'clause_explanations', ['document_id', 'clause_idx', 'style'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_clause_explanations_doc_clause_style', table_name='clause_explanations')
    op.drop_index(op.f('ix_clause_explanations_id'), table_name='clause_explanations')
    op.drop_table('clause_explanations')
