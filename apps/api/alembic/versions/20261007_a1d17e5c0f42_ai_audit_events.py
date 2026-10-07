"""ai audit events: append-only, hash-chained audit trail of AI investigations

Revision ID: a1d17e5c0f42
Revises: cdf3f1983053
Create Date: 2026-10-07 09:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a1d17e5c0f42"
down_revision: str | Sequence[str] | None = "cdf3f1983053"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_audit_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("investigation_id", sa.Uuid(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("event", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("request_id", sa.Text(), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("prev_hash", sa.Text(), nullable=True),
        sa.Column("hash", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_audit_events")),
        sa.UniqueConstraint(
            "investigation_id", "seq", name=op.f("uq_ai_audit_events_investigation_id_seq")
        ),
    )
    op.create_index(
        "ix_ai_audit_events_org_investigation",
        "ai_audit_events",
        ["org_id", "investigation_id"],
    )
    # Append-only: the audit trail can be added to, never changed or removed.
    op.execute(
        """
        CREATE FUNCTION ai_audit_events_append_only() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'ai_audit_events is append-only (% rejected)', TG_OP;
        END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER ai_audit_events_append_only
            BEFORE UPDATE OR DELETE ON ai_audit_events
            FOR EACH ROW EXECUTE FUNCTION ai_audit_events_append_only();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS ai_audit_events_append_only ON ai_audit_events")
    op.execute("DROP FUNCTION IF EXISTS ai_audit_events_append_only()")
    op.drop_index("ix_ai_audit_events_org_investigation", table_name="ai_audit_events")
    op.drop_table("ai_audit_events")
