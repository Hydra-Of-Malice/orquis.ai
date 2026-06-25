"""
Alembic initial migration — creates all tables for Zapper PM.
Run with: docker compose exec backend alembic upgrade head
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

# revision identifiers, used by Alembic.
revision = '001_initial_schema'
down_revision = None
branch_labels = None
depends_on = None



def upgrade():
    # Enable pgvector and UUID gen
    op.execute("CREATE EXTENSION IF NOT EXISTS \"pgcrypto\"")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ── orgs ──────────────────────────────────────────────────────────────────
    op.create_table("orgs",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.Text(), nullable=False, unique=True),
        sa.Column("slug", sa.Text(), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # ── users ─────────────────────────────────────────────────────────────────
    op.create_table("users",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.Text(), nullable=False, unique=True),
        sa.Column("hashed_password", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("avatar_url", sa.Text()),
        sa.Column("role", sa.String(20), server_default="member"),
        sa.Column("org_id", UUID(), sa.ForeignKey("orgs.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # ── meetings ──────────────────────────────────────────────────────────────
    op.create_table("meetings",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", UUID(), sa.ForeignKey("orgs.id"), nullable=True),
        sa.Column("created_by", UUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("title", sa.Text()),
        sa.Column("meeting_url", sa.Text()),
        sa.Column("platform", sa.String(10), server_default="meet"),
        sa.Column("status", sa.String(20), server_default="joining"),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("duration_seconds", sa.Integer()),
        sa.Column("participant_names", ARRAY(sa.Text()), server_default=sa.text("ARRAY[]::text[]")),
        sa.Column("participant_count", sa.Integer(), server_default=sa.text("0")),
        sa.Column("bot_slot_index", sa.Integer()),
        sa.Column("wav_path", sa.Text()),
        sa.Column("video_path", sa.Text()),
        sa.Column("audio_size_bytes", sa.BigInteger()),
        sa.Column("visual_capture_mode", sa.Text(), server_default="disabled"),
        sa.Column("health_score", sa.Integer()),
        sa.Column("engagement_score", sa.Integer()),
        sa.Column("sentiment", sa.Text()),
        sa.Column("summary_md", sa.Text()),
        sa.Column("summary_json", JSONB()),
        sa.Column("zapper_muted", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_meetings_org_status", "meetings", ["org_id", "status"])
    op.create_index("ix_meetings_created_at", "meetings", ["created_at"])

    # ── transcript_segments ───────────────────────────────────────────────────
    op.create_table("transcript_segments",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("meeting_id", UUID(), sa.ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("speaker_name", sa.Text(), nullable=False),
        sa.Column("speaker_id", sa.Text()),
        sa.Column("start_ms", sa.Integer(), nullable=False),
        sa.Column("end_ms", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), server_default="1.0"),
        sa.Column("words", JSONB()),
        sa.Column("embedding", JSONB()),  # float[] stored as JSONB; pgvector ops via raw SQL
    )
    op.create_index("ix_transcript_meeting_start", "transcript_segments", ["meeting_id", "start_ms"])

    # ── action_items ──────────────────────────────────────────────────────────
    op.create_table("action_items",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("meeting_id", UUID(), sa.ForeignKey("meetings.id", ondelete="SET NULL"), nullable=True),
        sa.Column("org_id", UUID(), sa.ForeignKey("orgs.id"), nullable=True),
        sa.Column("created_by", UUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("assignee_id", UUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("assignee_name", sa.Text()),
        sa.Column("status", sa.String(20), server_default="todo"),
        sa.Column("priority", sa.String(10), server_default="medium"),
        sa.Column("due_date", sa.Date()),
        sa.Column("jira_id", sa.Text()),
        sa.Column("linear_id", sa.Text()),
        sa.Column("notion_id", sa.Text()),
        sa.Column("source", sa.String(15), server_default="transcript"),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_action_items_org_status", "action_items", ["org_id", "status"])

    # ── chat_sessions ─────────────────────────────────────────────────────────
    op.create_table("chat_sessions",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("meeting_id", UUID(), sa.ForeignKey("meetings.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # ── chat_messages ─────────────────────────────────────────────────────────
    op.create_table("chat_messages",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", UUID(), sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(10), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("citations", JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # ── meeting_analytics ─────────────────────────────────────────────────────
    op.create_table("meeting_analytics",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("meeting_id", UUID(), sa.ForeignKey("meetings.id", ondelete="CASCADE"), unique=True, nullable=False),
        sa.Column("engagement_score", sa.Integer()),
        sa.Column("health_score", sa.Integer()),
        sa.Column("sentiment_score", sa.Float()),
        sa.Column("sentiment_timeline", JSONB()),
        sa.Column("talk_time_per_speaker", JSONB()),
        sa.Column("action_item_count", sa.Integer(), server_default=sa.text("0")),
        sa.Column("decisions_count", sa.Integer(), server_default=sa.text("0")),
        sa.Column("word_count", sa.Integer(), server_default=sa.text("0")),
        sa.Column("questions_count", sa.Integer(), server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # ── coaching_scores ───────────────────────────────────────────────────────
    op.create_table("coaching_scores",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("talk_ratio", sa.Float()),
        sa.Column("questions_asked", sa.Integer(), server_default=sa.text("0")),
        sa.Column("action_items_completed", sa.Integer(), server_default=sa.text("0")),
        sa.Column("meetings_attended", sa.Integer(), server_default=sa.text("0")),
        sa.Column("engagement_avg", sa.Float()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("user_id", "week_start", name="uq_coaching_user_week"),
    )

    # ── speaker_profiles ──────────────────────────────────────────────────────
    op.create_table("speaker_profiles",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", UUID(), sa.ForeignKey("orgs.id"), nullable=True),
        sa.Column("user_id", UUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("embedding", JSONB()),
        sa.Column("sample_count", sa.Integer(), server_default=sa.text("1")),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # ── meeting_speaker_tracks ────────────────────────────────────────────────
    op.create_table("meeting_speaker_tracks",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("meeting_id", UUID(), sa.ForeignKey("meetings.id"), nullable=False),
        sa.Column("track_label", sa.Text(), nullable=False),
        sa.Column("assigned_name", sa.Text(), nullable=False),
        sa.Column("matched_profile_id", UUID(), sa.ForeignKey("speaker_profiles.id"), nullable=True),
        sa.Column("confidence", sa.Float()),
        sa.Column("embedding", JSONB()),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("source", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # ── integration_tokens ────────────────────────────────────────────────────
    op.create_table("integration_tokens",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("org_id", UUID(), sa.ForeignKey("orgs.id"), nullable=True),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("access_token_enc", sa.LargeBinary()),
        sa.Column("refresh_token_enc", sa.LargeBinary()),
        sa.Column("token_expires_at", sa.DateTime(timezone=True)),
        sa.Column("scope", sa.Text()),
        sa.Column("metadata", JSONB()),
        sa.Column("connected_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # ── calendar_events ───────────────────────────────────────────────────────
    op.create_table("calendar_events",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("provider_event_id", sa.Text(), nullable=False),
        sa.Column("title", sa.Text()),
        sa.Column("start_time", sa.DateTime(timezone=True)),
        sa.Column("end_time", sa.DateTime(timezone=True)),
        sa.Column("meeting_url", sa.Text()),
        sa.Column("platform", sa.String(10)),
        sa.Column("attendees", JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("status", sa.String(30), server_default="synced"),
        sa.Column("meeting_id", UUID(), sa.ForeignKey("meetings.id"), nullable=True),
        sa.Column("celery_task_id", sa.Text()),
        sa.Column("raw_event_json", JSONB()),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # ── automations ───────────────────────────────────────────────────────────
    op.create_table("automations",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", UUID(), sa.ForeignKey("orgs.id"), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("trigger_type", sa.Text(), nullable=False),
        sa.Column("action_type", sa.Text(), nullable=False),
        sa.Column("params", JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # ── app_settings ──────────────────────────────────────────────────────────
    op.create_table("app_settings",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("value", sa.Text()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # ── audit_log ─────────────────────────────────────────────────────────────
    op.create_table("audit_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", UUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("resource_type", sa.Text()),
        sa.Column("resource_id", UUID(), nullable=True),
        sa.Column("meta", JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )


def downgrade():
    tables = [
        "audit_log", "app_settings", "automations", "calendar_events",
        "integration_tokens", "meeting_speaker_tracks", "speaker_profiles",
        "coaching_scores", "meeting_analytics", "chat_messages", "chat_sessions",
        "action_items", "transcript_segments", "meetings", "users", "orgs",
    ]
    for t in tables:
        op.drop_table(t)
