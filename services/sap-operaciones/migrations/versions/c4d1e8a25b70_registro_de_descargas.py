"""registro de descargas

Revision ID: c4d1e8a25b70
Revises: b2ff238c4818
Create Date: 2026-10-28 09:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4d1e8a25b70'
down_revision: Union[str, Sequence[str], None] = 'b2ff238c4818'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _audit_columns() -> list[sa.Column]:
    return [
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_by', sa.String(length=36), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_by', sa.String(length=36), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('deleted_by', sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['sap_operaciones.actors.id'], ),
        sa.ForeignKeyConstraint(['deleted_by'], ['sap_operaciones.actors.id'], ),
        sa.ForeignKeyConstraint(['updated_by'], ['sap_operaciones.actors.id'], ),
        sa.PrimaryKeyConstraint('id'),
    ]


def upgrade() -> None:
    """Aplica los cambios de esta revisión."""
    op.create_table('document_downloads',
    sa.Column('company_id', sa.String(length=36), nullable=False),
    sa.Column('company_db', sa.String(length=100), nullable=False),
    sa.Column('mode', sa.String(length=20), nullable=False),
    sa.Column('file_count', sa.Integer(), nullable=False),
    sa.Column('trace_id', sa.String(length=36), nullable=True),
    *_audit_columns(),
    sa.CheckConstraint("mode IN ('single', 'sequential', 'zip')", name='ck_document_downloads_mode'),
    schema='sap_operaciones'
    )
    op.create_index('ix_document_downloads_company_created', 'document_downloads', ['company_id', 'created_at'], unique=False, schema='sap_operaciones')
    op.create_index('ix_document_downloads_created_by', 'document_downloads', ['created_by', 'created_at'], unique=False, schema='sap_operaciones')
    op.create_table('document_download_files',
    sa.Column('download_id', sa.String(length=36), nullable=False),
    sa.Column('seq', sa.Integer(), nullable=False),
    sa.Column('type_code', sa.String(length=10), nullable=False),
    sa.Column('doc_entry', sa.Integer(), nullable=False),
    sa.Column('doc_num', sa.Integer(), nullable=True),
    sa.Column('attachment_entry', sa.Integer(), nullable=False),
    sa.Column('line', sa.Integer(), nullable=False),
    sa.Column('file_name', sa.String(length=200), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('error', sa.String(length=300), nullable=True),
    *_audit_columns(),
    sa.CheckConstraint("status IN ('pending', 'delivered', 'failed')", name='ck_document_download_files_status'),
    sa.ForeignKeyConstraint(['download_id'], ['sap_operaciones.document_downloads.id'], ),
    sa.UniqueConstraint('download_id', 'seq'),
    schema='sap_operaciones'
    )


def downgrade() -> None:
    """Los retrocesos destructivos requieren una decisión explícita."""
    raise RuntimeError(
        "Downgrade deshabilitado; preparar una migración correctiva."
    )
