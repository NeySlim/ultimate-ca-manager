"""
Migration 040 - Create discovered_certificate table
"""
from datetime import datetime
import sqlalchemy as sa
from alembic import op


def upgrade():
    op.create_table(
        'discovered_certificate',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('target', sa.String(length=1024), nullable=False),
        sa.Column('certificate', sa.Text(), nullable=False),
        sa.Column('issuer', sa.String(length=1024), nullable=True),
        sa.Column('subject', sa.String(length=1024), nullable=True),
        sa.Column('serial', sa.String(length=64), nullable=True),
        sa.Column('not_before', sa.DateTime(), nullable=True),
        sa.Column('not_after', sa.DateTime(), nullable=True),
        sa.Column('fingerprint', sa.String(length=64), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='unknown'),
        sa.Column('last_seen', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('ucm_certificate_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['ucm_certificate_id'], ['certificate.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('fingerprint', name='uq_discovered_certificate_fingerprint'),
        sa.Index('ix_discovered_certificate_target', 'target'),
        sa.Index('ix_discovered_certificate_serial', 'serial'),
        sa.Index('ix_discovered_certificate_status', 'status'),
        sa.Index('ix_discovered_certificate_last_seen', 'last_seen'),
    )
    
    op.create_index(
        'ix_discovered_certificate_fingerprint',
        'discovered_certificate',
        ['fingerprint'],
        unique=False
    )


def downgrade():
    op.drop_table('discovered_certificate')
