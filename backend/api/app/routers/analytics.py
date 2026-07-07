"""
Analytics router — overview KPIs, team insights, personal coaching.
"""
from datetime import date, timedelta, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.auth import get_current_user
from app.models.models import Meeting, ActionItem, MeetingAnalytics, CoachingScore, User

router = APIRouter(tags=["Analytics"])


@router.get("/analytics/overview")
async def analytics_overview(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = current_user.org_id

    # Total meetings done
    total_r = await db.execute(
        select(func.count()).where(Meeting.org_id == org_id, Meeting.status == "done")
    )
    total_meetings = total_r.scalar() or 0

    # Average meeting duration (hours saved calc: avg 30 min per manual note taking saved)
    dur_r = await db.execute(
        select(func.avg(Meeting.duration_seconds)).where(
            Meeting.org_id == org_id, Meeting.status == "done", Meeting.duration_seconds.isnot(None)
        )
    )
    avg_duration = dur_r.scalar() or 0

    # Action items stats
    total_ai_r = await db.execute(
        select(func.count()).where(ActionItem.org_id == org_id)
    )
    done_ai_r = await db.execute(
        select(func.count()).where(ActionItem.org_id == org_id, ActionItem.status == "done")
    )
    total_ai = total_ai_r.scalar() or 0
    done_ai = done_ai_r.scalar() or 0
    completion_rate = round((done_ai / total_ai * 100) if total_ai else 0)

    # Average health score
    health_r = await db.execute(
        select(func.avg(Meeting.health_score)).where(
            Meeting.org_id == org_id, Meeting.health_score.isnot(None)
        )
    )
    avg_health = round(health_r.scalar() or 0)

    # Hours saved (30 min per meeting = time not manually taking notes)
    hours_saved = round(total_meetings * 0.5, 1)

    # This week's meetings
    week_start = date.today() - timedelta(days=date.today().weekday())
    week_r = await db.execute(
        select(func.count()).where(
            Meeting.org_id == org_id,
            Meeting.status == "done",
            Meeting.started_at >= datetime(week_start.year, week_start.month, week_start.day, tzinfo=timezone.utc),
        )
    )
    meetings_this_week = week_r.scalar() or 0

    # Recent AI insights (from summary_json)
    recent_r = await db.execute(
        select(Meeting)
        .where(Meeting.org_id == org_id, Meeting.status == "done", Meeting.summary_json.isnot(None))
        .order_by(Meeting.created_at.desc())
        .limit(5)
    )
    recent = recent_r.scalars().all()
    insights = []
    for r in recent:
        if isinstance(r.summary_json, dict) and r.summary_json.get("key_topics"):
            for topic in (r.summary_json.get("key_topics") or [])[:2]:
                if isinstance(topic, dict):
                    insights.append({
                        "meeting": r.title,
                        "topic": topic.get("topic", ""),
                        "detail": topic.get("detail", "")[:100],
                    })

    # Calculate MoM Deltas
    now = datetime.now(timezone.utc)
    thirty_days_ago = now - timedelta(days=30)
    sixty_days_ago = now - timedelta(days=60)

    # 1. Meetings count deltas
    this_month_meetings_r = await db.execute(
        select(func.count()).where(
            Meeting.org_id == org_id,
            Meeting.status == "done",
            Meeting.started_at >= thirty_days_ago
        )
    )
    this_month_meetings = this_month_meetings_r.scalar() or 0

    last_month_meetings_r = await db.execute(
        select(func.count()).where(
            Meeting.org_id == org_id,
            Meeting.status == "done",
            Meeting.started_at >= sixty_days_ago,
            Meeting.started_at < thirty_days_ago
        )
    )
    last_month_meetings = last_month_meetings_r.scalar() or 0

    if last_month_meetings == 0:
        total_meetings_delta = 100 if this_month_meetings > 0 else 0
    else:
        total_meetings_delta = round(((this_month_meetings - last_month_meetings) / last_month_meetings) * 100)

    # 2. Meeting duration (hours) deltas
    this_month_duration_r = await db.execute(
        select(func.sum(Meeting.duration_seconds)).where(
            Meeting.org_id == org_id,
            Meeting.status == "done",
            Meeting.started_at >= thirty_days_ago,
            Meeting.duration_seconds.isnot(None)
        )
    )
    this_month_duration = (this_month_duration_r.scalar() or 0) / 3600

    last_month_duration_r = await db.execute(
        select(func.sum(Meeting.duration_seconds)).where(
            Meeting.org_id == org_id,
            Meeting.status == "done",
            Meeting.started_at >= sixty_days_ago,
            Meeting.started_at < thirty_days_ago,
            Meeting.duration_seconds.isnot(None)
        )
    )
    last_month_duration = (last_month_duration_r.scalar() or 0) / 3600

    if last_month_duration == 0:
        total_hours_delta = 100 if this_month_duration > 0 else 0
    else:
        total_hours_delta = round(((this_month_duration - last_month_duration) / last_month_duration) * 100)

    return {
        "total_meetings": total_meetings,
        "meetings_this_week": meetings_this_week,
        "hours_saved": hours_saved,
        "action_item_completion_rate": completion_rate,
        "total_action_items": total_ai,
        "avg_health_score": avg_health,
        "avg_meeting_duration_mins": round(avg_duration / 60) if avg_duration else 0,
        "recent_insights": insights[:6],
        "total_meetings_delta": total_meetings_delta,
        "total_hours_delta": total_hours_delta,
    }


@router.get("/analytics/team")
async def analytics_team(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = current_user.org_id

    # All meetings with analytics
    result = await db.execute(
        select(Meeting, MeetingAnalytics)
        .join(MeetingAnalytics, MeetingAnalytics.meeting_id == Meeting.id, isouter=True)
        .where(Meeting.org_id == org_id, Meeting.status == "done")
        .order_by(Meeting.created_at.desc())
        .limit(50)
    )
    rows = result.all()

    # Aggregate talk time per speaker across all meetings
    speaker_stats: dict = {}
    for meeting, analytics in rows:
        if analytics and analytics.talk_time_per_speaker:
            for speaker, secs in analytics.talk_time_per_speaker.items():
                if speaker not in speaker_stats:
                    speaker_stats[speaker] = {
                        "name": speaker,
                        "total_talk_seconds": 0,
                        "meetings_count": 0,
                        "avg_engagement": [],
                    }
                speaker_stats[speaker]["total_talk_seconds"] += secs
                speaker_stats[speaker]["meetings_count"] += 1
                if analytics.engagement_score:
                    speaker_stats[speaker]["avg_engagement"].append(analytics.engagement_score)

    team_members = []
    for name, stats in speaker_stats.items():
        avg_eng = (
            round(sum(stats["avg_engagement"]) / len(stats["avg_engagement"]))
            if stats["avg_engagement"] else None
        )
        team_members.append({
            "name": name,
            "meetings_count": stats["meetings_count"],
            "total_talk_minutes": round(stats["total_talk_seconds"] / 60, 1),
            "avg_engagement_score": avg_eng,
        })

    # Sort by meetings attended descending
    team_members.sort(key=lambda x: x["meetings_count"], reverse=True)

    # Meeting frequency heatmap (last 30 days)
    thirty_ago = datetime.now(timezone.utc) - timedelta(days=30)
    recent_meetings_r = await db.execute(
        select(Meeting.started_at, Meeting.health_score)
        .where(Meeting.org_id == org_id, Meeting.started_at >= thirty_ago, Meeting.status == "done")
    )
    heatmap_data = [
        {"date": r.started_at.date().isoformat(), "count": 1, "health_score": r.health_score}
        for r in recent_meetings_r.all()
        if r.started_at
    ]

    return {
        "team_members": team_members[:20],
        "heatmap": heatmap_data,
    }


@router.get("/analytics/coaching")
async def analytics_coaching(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Personal coaching scores last 8 weeks
    eight_weeks_ago = date.today() - timedelta(weeks=8)
    scores_r = await db.execute(
        select(CoachingScore)
        .where(
            CoachingScore.user_id == current_user.id,
            CoachingScore.week_start >= eight_weeks_ago,
        )
        .order_by(CoachingScore.week_start)
    )
    scores = scores_r.scalars().all()

    # Current week summary from meetings
    week_start = date.today() - timedelta(days=date.today().weekday())
    week_meetings_r = await db.execute(
        select(Meeting)
        .where(
            Meeting.org_id == current_user.org_id,
            Meeting.status == "done",
            Meeting.started_at >= datetime(week_start.year, week_start.month, week_start.day, tzinfo=timezone.utc),
        )
    )
    week_meetings = week_meetings_r.scalars().all()

    # Action items completed this week by this user
    week_done_r = await db.execute(
        select(func.count()).where(
            ActionItem.assignee_id == current_user.id,
            ActionItem.status == "done",
            ActionItem.updated_at >= datetime(week_start.year, week_start.month, week_start.day, tzinfo=timezone.utc),
        )
    )
    actions_completed = week_done_r.scalar() or 0

    return {
        "weekly_scores": [
            {
                "week_start": s.week_start.isoformat(),
                "talk_ratio": s.talk_ratio,
                "questions_asked": s.questions_asked,
                "action_items_completed": s.action_items_completed,
                "meetings_attended": s.meetings_attended,
                "engagement_avg": s.engagement_avg,
            }
            for s in scores
        ],
        "current_week": {
            "meetings_attended": len(week_meetings),
            "actions_completed": actions_completed,
        },
    }


@router.get("/analytics/heatmap")
async def analytics_heatmap(
    weeks: int = 52,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Meeting frequency heatmap data for the past N weeks."""
    since = datetime.now(timezone.utc) - timedelta(weeks=weeks)
    result = await db.execute(
        select(Meeting.started_at)
        .where(
            Meeting.org_id == current_user.org_id,
            Meeting.started_at >= since,
            Meeting.status == "done",
        )
        .order_by(Meeting.started_at)
    )
    dates = [r.started_at.date().isoformat() for r in result.all() if r.started_at]

    # Count meetings per date
    counts: dict = {}
    for d in dates:
        counts[d] = counts.get(d, 0) + 1

    return [{"date": d, "count": c} for d, c in sorted(counts.items())]
