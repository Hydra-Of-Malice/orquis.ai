"""
Migration 002 — Adds automation_rules table with full multi-action schema.
The original 'automations' table stays (backward-compat) but the new router
uses 'automation_rules' which supports JSONB conditions + actions arrays.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = '002_automation_rules'
down_revision = '001_initial_schema'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "automation_rules",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", UUID(), sa.ForeignKey("orgs.id"), nullable=True),
        sa.Column("created_by", UUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("trigger", sa.Text(), nullable=False),
        # meeting.ended | action_item.created | decision.detected
        sa.Column("conditions", JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("actions", JSONB(), server_default=sa.text("'[]'::jsonb")),
        # [{type: "create_jira_ticket", config: {...}}, ...]
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_automation_rules_org", "automation_rules", ["org_id"])
    op.create_index("ix_automation_rules_trigger", "automation_rules", ["trigger"])


def downgrade():
    op.drop_index("ix_automation_rules_trigger", "automation_rules")
    op.drop_index("ix_automation_rules_org", "automation_rules")
    op.drop_table("automation_rules")
