"""ajout role auditeur

Revision ID: ab757804bbf7
Revises: 56e1a05bcbec
"""
from alembic import op

revision = "ab757804bbf7"
down_revision = "56e1a05bcbec"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TYPE roleutilisateur ADD VALUE IF NOT EXISTS 'auditeur'")


def downgrade():
    pass
