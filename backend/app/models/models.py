"""
All SQLAlchemy ORM models for Zapper PM.
Schema managed by Alembic migrations — no create_all here.
"""
import uuid

from sqlalchemy import (
    BigInteger, Boolean, Column, Date, DateTime, Float,
    ForeignKey, Integer, LargeBinary, String, Text, func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import relationship

from app.db import Base


def new_uuid() -> str:
    return str(uuid.uuid4())


# ── Organizations ──────────────────────────────────────────────────────────────

class Org(Base):
    __tablename__ = "orgs"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    name = Column(Text, nullable=False, unique=True)
    slug = Column(Text, nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    users = relationship("User", back_populates="org")
    meetings = relationship("Meeting", back_populates="org")


# ── Users ──────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    email = Column(Text, nullable=False, unique=True)
    hashed_password = Column(Text, nullable=False)
    display_name = Column(Text, nullable=False)
    avatar_url = Column(Text, nullable=True)
    role = Column(String(20), default="member")  # 'admin' | 'member'
    org_id = Column(UUID(as_uuid=False), ForeignKey("orgs.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    org = relationship("Org", back_populates="users")
    action_items_created = relationship("ActionItem", foreign_keys="ActionItem.created_by", back_populates="creator")
    action_items_assigned = relationship("ActionItem", foreign_keys="ActionItem.assignee_id", back_populates="assignee")
    chat_sessions = relationship("ChatSession", back_populates="user")
    coaching_scores = relationship("CoachingScore", back_populates="user")
    integration_tokens = relationship("IntegrationToken", back_populates="user")
    calendar_events = relationship("CalendarEvent", back_populates="user")


# ── Meetings ───────────────────────────────────────────────────────────────────

class Meeting(Base):
    __tablename__ = "meetings"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    org_id = Column(UUID(as_uuid=False), ForeignKey("orgs.id"), nullable=True)
    created_by = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)
    title = Column(Text)
    meeting_url = Column(Text)
    platform = Column(String(10), default="meet")  # 'meet' | 'teams'
    status = Column(String(20), default="joining")
    # joining | lobby | recording | processing | done | error
    started_at = Column(DateTime(timezone=True))
    ended_at = Column(DateTime(timezone=True))
    duration_seconds = Column(Integer)
    participant_names = Column(ARRAY(Text), default=list)
    participant_count = Column(Integer, default=0)
    bot_slot_index = Column(Integer)
    wav_path = Column(Text)
    video_path = Column(Text)
    audio_size_bytes = Column(BigInteger)
    visual_capture_mode = Column(Text, nullable=False, default="disabled")
    health_score = Column(Integer)
    engagement_score = Column(Integer)
    sentiment = Column(Text)
    summary_md = Column(Text)
    summary_json = Column(JSONB)
    zapper_muted = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    org = relationship("Org", back_populates="meetings")
    transcript_segments = relationship("TranscriptSegment", back_populates="meeting", cascade="all, delete-orphan")
    action_items = relationship("ActionItem", back_populates="meeting")
    analytics = relationship("MeetingAnalytics", back_populates="meeting", uselist=False)
    chat_sessions = relationship("ChatSession", back_populates="meeting")
    calendar_event = relationship("CalendarEvent", back_populates="meeting", uselist=False)
    speaker_tracks = relationship("MeetingSpeakerTrack", back_populates="meeting", cascade="all, delete-orphan")


# ── Transcript Segments ────────────────────────────────────────────────────────

class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    meeting_id = Column(UUID(as_uuid=False), ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False)
    speaker_name = Column(Text, nullable=False)
    speaker_id = Column(Text)  # 'Speaker_A', 'Speaker_B', etc.
    start_ms = Column(Integer, nullable=False)
    end_ms = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    confidence = Column(Float, default=1.0)
    words = Column(JSONB)
    # embedding stored as JSONB float array (pgvector type handled via raw SQL)

    meeting = relationship("Meeting", back_populates="transcript_segments")


# ── Action Items ───────────────────────────────────────────────────────────────

class ActionItem(Base):
    __tablename__ = "action_items"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    meeting_id = Column(UUID(as_uuid=False), ForeignKey("meetings.id", ondelete="SET NULL"), nullable=True)
    org_id = Column(UUID(as_uuid=False), ForeignKey("orgs.id"), nullable=True)
    created_by = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)
    title = Column(Text, nullable=False)
    description = Column(Text)
    assignee_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)
    assignee_name = Column(Text)
    status = Column(String(20), default="todo")    # todo | in_progress | done
    priority = Column(String(10), default="medium")  # urgent | high | medium | low
    due_date = Column(Date)
    jira_id = Column(Text)
    linear_id = Column(Text)
    notion_id = Column(Text)
    source = Column(String(15), default="transcript")  # transcript | manual | ai
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    meeting = relationship("Meeting", back_populates="action_items")
    creator = relationship("User", foreign_keys=[created_by], back_populates="action_items_created")
    assignee = relationship("User", foreign_keys=[assignee_id], back_populates="action_items_assigned")


# ── AI Chat ────────────────────────────────────────────────────────────────────

class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)
    meeting_id = Column(UUID(as_uuid=False), ForeignKey("meetings.id", ondelete="SET NULL"), nullable=True)
    title = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="chat_sessions")
    meeting = relationship("Meeting", back_populates="chat_sessions")
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    session_id = Column(UUID(as_uuid=False), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(10), nullable=False)  # 'user' | 'assistant'
    content = Column(Text, nullable=False)
    citations = Column(JSONB)  # [{meeting_id, segment_id, speaker, snippet, start_ms}]
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    session = relationship("ChatSession", back_populates="messages")


# ── Analytics ──────────────────────────────────────────────────────────────────

class MeetingAnalytics(Base):
    __tablename__ = "meeting_analytics"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    meeting_id = Column(UUID(as_uuid=False), ForeignKey("meetings.id", ondelete="CASCADE"), unique=True, nullable=False)
    engagement_score = Column(Integer)
    health_score = Column(Integer)
    sentiment_score = Column(Float)
    sentiment_timeline = Column(JSONB)   # [{minute, score}]
    talk_time_per_speaker = Column(JSONB)  # {speaker_name: seconds}
    action_item_count = Column(Integer, default=0)
    decisions_count = Column(Integer, default=0)
    word_count = Column(Integer, default=0)
    questions_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    meeting = relationship("Meeting", back_populates="analytics")


class CoachingScore(Base):
    __tablename__ = "coaching_scores"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    week_start = Column(Date, nullable=False)
    talk_ratio = Column(Float)
    questions_asked = Column(Integer, default=0)
    action_items_completed = Column(Integer, default=0)
    meetings_attended = Column(Integer, default=0)
    engagement_avg = Column(Float)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="coaching_scores")


# ── Speaker Profiles ───────────────────────────────────────────────────────────

class SpeakerProfile(Base):
    __tablename__ = "speaker_profiles"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    org_id = Column(UUID(as_uuid=False), ForeignKey("orgs.id"), nullable=True)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)
    display_name = Column(Text, nullable=False)
    embedding = Column(JSONB)   # ECAPA-TDNN voice fingerprint (192-dim float array)
    sample_count = Column(Integer, default=1)
    last_seen_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class MeetingSpeakerTrack(Base):
    """Ephemeral per-meeting speaker track (Speaker_A, Speaker_B…)."""
    __tablename__ = "meeting_speaker_tracks"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    meeting_id = Column(UUID(as_uuid=False), ForeignKey("meetings.id"), nullable=False)
    track_label = Column(Text, nullable=False)     # "Speaker_A"
    assigned_name = Column(Text, nullable=False)   # "John Smith" or "Unknown 1"
    matched_profile_id = Column(UUID(as_uuid=False), ForeignKey("speaker_profiles.id"), nullable=True)
    confidence = Column(Float, nullable=True)
    embedding = Column(JSONB, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    source = Column(Text, nullable=True)           # 'voice_match' | 'from_intro' | 'manual'
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    meeting = relationship("Meeting", back_populates="speaker_tracks")


# ── Integrations ───────────────────────────────────────────────────────────────

class IntegrationToken(Base):
    __tablename__ = "integration_tokens"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    org_id = Column(UUID(as_uuid=False), ForeignKey("orgs.id"), nullable=True)
    provider = Column(Text, nullable=False)
    # google_calendar | outlook | jira | slack | notion | linear
    access_token_enc = Column(LargeBinary)
    refresh_token_enc = Column(LargeBinary)
    token_expires_at = Column(DateTime(timezone=True))
    scope = Column(Text)
    metadata_ = Column("metadata", JSONB)
    connected_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="integration_tokens")


# ── Calendar Events ────────────────────────────────────────────────────────────

class CalendarEvent(Base):
    __tablename__ = "calendar_events"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    provider_event_id = Column(Text, nullable=False)
    title = Column(Text)
    start_time = Column(DateTime(timezone=True))
    end_time = Column(DateTime(timezone=True))
    meeting_url = Column(Text)
    platform = Column(String(10))
    attendees = Column(JSONB, default=list)
    status = Column(String(30), default="synced")
    meeting_id = Column(UUID(as_uuid=False), ForeignKey("meetings.id"), nullable=True)
    celery_task_id = Column(Text)
    raw_event_json = Column(JSONB)
    last_synced_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="calendar_events")
    meeting = relationship("Meeting", back_populates="calendar_event")


# ── Automations ────────────────────────────────────────────────────────────────

class Automation(Base):
    __tablename__ = "automations"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    org_id = Column(UUID(as_uuid=False), ForeignKey("orgs.id"), nullable=True)
    name = Column(Text, nullable=False)
    trigger_type = Column(Text, nullable=False)
    # meeting_ended | keyword_detected | action_item_created
    action_type = Column(Text, nullable=False)
    # send_slack | create_jira | send_email | auto_join
    params = Column(JSONB, default=dict)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ── App Settings ───────────────────────────────────────────────────────────────

class AppSetting(Base):
    __tablename__ = "app_settings"

    key = Column(Text, primary_key=True)
    value = Column(Text)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# ── Audit Log ──────────────────────────────────────────────────────────────────

class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)
    action = Column(Text, nullable=False)
    resource_type = Column(Text)
    resource_id = Column(UUID(as_uuid=False), nullable=True)
    meta = Column(JSONB)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
