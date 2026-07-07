import React, { useState, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useAuthStore } from "../store/authStore";
import { meetingsApi } from "../services/meetings";
import { tasksApi } from "../services/tasks";
import { analyticsApi } from "../services/analytics";
import { PageHeader } from "../components/layout/PageHeader";
import { Card } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { Avatar } from "../components/ui/Avatar";
import { Badge } from "../components/ui/Badge";
import { AreaChart } from "../components/charts/AreaChart";
import { BarChart } from "../components/charts/BarChart";
import { ContributionGrid } from "../components/charts/ContributionGrid";
import { Modal } from "../components/ui/Modal";
import { Input } from "../components/ui/Input";
import { StatCard } from "../components/ui/StatCard";
import { JoinMeetingModal } from "../components/modals/JoinMeetingModal";
import { ProgressRing } from "../components/ui/ProgressRing";
import {
  Plus,
  Upload,
  Calendar,
  Clock,
  ArrowRight,
  CheckSquare,
  Brain,
  Sparkles,
  MessageSquare,
  ListTodo,
  Loader2
} from "lucide-react";
import styles from "./Dashboard.module.css";
import clsx from "clsx";

interface DashboardProps {
  onOpenCommandPalette?: () => void;
}

// Dynamic Meeting Widget
const MeetingWidget: React.FC<{ liveMeeting?: any, lastMeeting?: any }> = ({ liveMeeting, lastMeeting }) => {
  if (liveMeeting) {
    return (
      <div className={styles.countdownBox}>
        <div className={styles.countdownHeader}>
          <span className={styles.pulseDot} />
          <span className={styles.countdownTitle}>Active Meeting</span>
        </div>
        <div className={styles.countdownVal} style={{ fontSize: '1.25rem', marginBottom: '8px' }}>
          {liveMeeting.title || "Untitled Meeting"}
        </div>
        <div className={styles.countdownMeta}>
          <span className={styles.countdownName}>{liveMeeting.platform === 'meet' ? 'Google Meet' : 'Zoom'}</span>
          <span className={styles.countdownPlatform}>{liveMeeting.status === 'recording' ? 'Recording in progress...' : 'Processing...'}</span>
        </div>
      </div>
    );
  }

  if (lastMeeting) {
    return (
      <div className={styles.countdownBox}>
        <div className={styles.countdownHeader}>
          <span className={styles.countdownTitle} style={{ color: 'var(--text-secondary)' }}>Last Recorded Meeting</span>
        </div>
        <div className={styles.countdownVal} style={{ fontSize: '1.25rem', marginBottom: '8px', lineHeight: 1.2 }}>
          {lastMeeting.title || "Untitled Meeting"}
        </div>
        <div className={styles.countdownMeta}>
          <span className={styles.countdownName}>{lastMeeting.duration_seconds ? Math.round(lastMeeting.duration_seconds / 60) + 'm duration' : 'Recent'}</span>
          <span className={styles.countdownPlatform}>{lastMeeting.participant_count || 1} participants</span>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.countdownBox}>
      <div className={styles.countdownHeader}>
        <span className={styles.countdownTitle} style={{ color: 'var(--text-secondary)' }}>No Meetings Yet</span>
      </div>
      <div className={styles.countdownVal} style={{ fontSize: '1rem', color: 'var(--text-tertiary)' }}>
        Join a call to get started.
      </div>
    </div>
  );
};

// Helper to clean up speaker names for display
const formatSpeakerName = (name: string) => {
  if (!name) return "Unknown";
  if (name.startsWith("Unknown")) {
    return name.replace("Unknown", "Speaker");
  }
  return name.split(' ')[0]; // First name only for real people
};

export const Dashboard: React.FC<DashboardProps> = ({ onOpenCommandPalette }) => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { user } = useAuthStore();

  // ── Real API data ──────────────────────────────────────────────────────────
  const { data: meetings = [] } = useQuery({
    queryKey: ['meetings'],
    queryFn: () => meetingsApi.list({ limit: 10 }),
    retry: 1,
  });

  const { data: taskStats } = useQuery({
    queryKey: ['task-stats'],
    queryFn: () => tasksApi.getStats(),
    retry: 1,
  });

  const { data: tasks = [] } = useQuery({
    queryKey: ['tasks', 'todo'],
    queryFn: () => tasksApi.list({ status: 'todo', limit: 4 }),
    retry: 1,
  });

  const { data: recentTasks = [] } = useQuery({
    queryKey: ['tasks', 'recent'],
    queryFn: () => tasksApi.list({ limit: 10 }),
    retry: 1,
  });

  const { data: overview } = useQuery({
    queryKey: ['analytics-overview'],
    queryFn: () => analyticsApi.getOverview({ days: 30 }),
    retry: 1,
  });

  const { data: teamData } = useQuery({
    queryKey: ['team-data'],
    queryFn: () => analyticsApi.getTeamMembers(),
    retry: 1,
  });

  // ── Modals state ───────────────────────────────────────────────────────────
  const [isJoinOpen, setIsJoinOpen] = useState(false);
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);

  // ── Greeting animation ─────────────────────────────────────────────────────
  const [greetingText, setGreetingText] = useState("");
  const hour = new Date().getHours();
  const timeOfDay = hour < 12 ? "morning" : hour < 18 ? "afternoon" : "evening";
  const firstName = user?.display_name?.split(' ')[0] || 'there';
  const fullGreeting = `Good ${timeOfDay}, ${firstName}`;

  useEffect(() => {
    let index = 0;
    const interval = setInterval(() => {
      setGreetingText(fullGreeting.slice(0, index + 1));
      index++;
      if (index >= fullGreeting.length) clearInterval(interval);
    }, 45);
    return () => clearInterval(interval);
  }, [fullGreeting]);

  const todayStr = new Date().toLocaleDateString("en-US", {
    weekday: "long", month: "short", day: "numeric", year: "numeric",
  });

  // ── Derived metrics ────────────────────────────────────────────────────────
  const liveMeeting = meetings.find((m) => m.status === "joining" || m.status === "lobby" || m.status === "recording" || m.status === "processing");
  const completedMeetings = meetings.filter((m) => m.status === "done");
  const lastMeeting = completedMeetings[0];
  const openTasks = taskStats?.todo ?? 0;
  const overdueTasks = taskStats?.overdue ?? 0;
  const avgHealth = overview?.avg_health_score ?? 0;

  const totalMeetingHours = React.useMemo(() => {
    if (!overview) return 0;
    const totalMins = (overview.avg_meeting_duration_mins || 0) * (overview.total_meetings || 0);
    return Math.round((totalMins / 60) * 10) / 10;
  }, [overview]);

  const meetingsSparkline = React.useMemo(() => {
    if (completedMeetings.length === 0) return [0, 0, 0, 0, 0, 0, 0];
    const counts = [0, 0, 0, 0, 0, 0, 0];
    const now = new Date();
    completedMeetings.forEach(m => {
      const diffTime = Math.abs(now.getTime() - new Date(m.created_at || Date.now()).getTime());
      const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24));
      if (diffDays < 7) {
        counts[6 - diffDays]++;
      }
    });
    // Cumulative progression
    const cumulative = [];
    let sum = 0;
    for (let i = 0; i < 7; i++) {
      sum += counts[i];
      cumulative.push(sum);
    }
    return cumulative;
  }, [completedMeetings]);

  const hoursSparkline = React.useMemo(() => {
    if (completedMeetings.length === 0) return [0, 0, 0, 0, 0, 0, 0];
    const hoursPerDay = [0, 0, 0, 0, 0, 0, 0];
    const now = new Date();
    completedMeetings.forEach(m => {
      const diffTime = Math.abs(now.getTime() - new Date(m.created_at || Date.now()).getTime());
      const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24));
      if (diffDays < 7) {
        hoursPerDay[6 - diffDays] += (m.duration_seconds || 0) / 3600;
      }
    });
    // Cumulative progression
    const cumulative = [];
    let sum = 0;
    for (let i = 0; i < 7; i++) {
      sum += hoursPerDay[i];
      cumulative.push(Math.round(sum * 10) / 10);
    }
    return cumulative;
  }, [completedMeetings]);

  const sentimentData = React.useMemo(() => {
    if (completedMeetings.length === 0) return [];
    // Take up to last 7 meetings, reverse chronological to chronological for the chart
    const recent = completedMeetings.slice(0, 7).reverse();
    const mapped = recent.map(m => ({
      name: new Date(m.created_at || Date.now()).toLocaleDateString('en-US', { weekday: 'short' }),
      value: m.health_score || 0
    }));

    // If only 1 meeting, prepend a baseline point so Recharts AreaChart renders correctly
    if (mapped.length === 1) {
      return [
        { name: "Start", value: 50 },
        mapped[0]
      ];
    }
    return mapped;
  }, [completedMeetings]);

  const speakingBalanceData = React.useMemo(() => {
    if (!teamData?.team_members?.length) return [];
    return teamData.team_members.slice(0, 4).map((member: any) => ({
      name: formatSpeakerName(member.name),
      value: member.total_talk_minutes
    }));
  }, [teamData]);

  const intelligenceFeed = React.useMemo(() => {
    const feed: any[] = [];
    completedMeetings.slice(0, 5).forEach(m => {
      feed.push({
        id: `m-${m.id}`,
        text: `Meeting **${m.title || 'Untitled'}** processed successfully.`,
        date: new Date(m.created_at || Date.now()),
        color: 'emerald'
      });
    });
    recentTasks.slice(0, 8).forEach((t: any) => {
      feed.push({
        id: `t-${t.id}`,
        text: t.status === 'done' 
          ? `Action item **"${t.title}"** marked as done.` 
          : `New action item **"${t.title}"** assigned to ${t.assignee_name || 'someone'}.`,
        date: new Date(t.created_at || Date.now()),
        color: t.status === 'done' ? 'purple' : 'indigo'
      });
    });
    return feed.sort((a, b) => b.date.getTime() - a.date.getTime()).slice(0, 4);
  }, [completedMeetings, recentTasks]);

  const proTip = React.useMemo(() => {
    if (overdueTasks > 0) {
      return `You have ${overdueTasks} overdue tasks. Consider dedicating 15 minutes today to clearing your backlog.`;
    }
    if (avgHealth > 0 && avgHealth < 70) {
      return `Your average meeting health is ${avgHealth}%. Try asking open-ended questions like "Mia, what are your thoughts?" to increase team engagement by 15%.`;
    }
    return `Your meeting health is looking great! Maintain this momentum by keeping discussions focused and action-oriented.`;
  }, [overdueTasks, avgHealth]);

  // ── Handlers ───────────────────────────────────────────────────────────────

  const handleUploadSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setUploadProgress(10);
    const interval = setInterval(() => {
      setUploadProgress((prev) => {
        if (prev === null) return null;
        if (prev >= 100) {
          clearInterval(interval);
          setTimeout(() => {
            setIsUploadOpen(false);
            setUploadProgress(null);
            navigate("/meetings/recordings");
          }, 500);
          return 100;
        }
        return prev + 15;
      });
    }, 150);
  };

  return (
    <div className={styles.container}>
      <PageHeader
        breadcrumbs={["Home", "Dashboard"]}
        onOpenCommandPalette={onOpenCommandPalette}
        actions={
          <div className={styles.headerActions}>
            <Button variant="outline" size="sm" icon={<Plus size={16} />} onClick={() => setIsJoinOpen(true)}>
              Join / Call Bot
            </Button>
            <Button variant="primary" size="sm" icon={<Upload size={16} />} onClick={() => setIsUploadOpen(true)}>
              Upload Recording
            </Button>
          </div>
        }
      />

      <div className={styles.content}>
        <div className={styles.dashboardLayout}>
          {/* Main Column */}
          <div className={styles.mainCol}>
            
            {/* Welcome Banner */}
            <div className={styles.welcomeBanner}>
              <div className={styles.welcomeText}>
                <h1 className={styles.typingHeader}>
                  {greetingText}
                  <span className={styles.cursor}>|</span>
                </h1>
                <p className={styles.date}>{todayStr}</p>
              </div>
              {liveMeeting && (
                <div className={styles.liveAlert} onClick={() => navigate(`/live/${liveMeeting.id}`)}>
                  <span className={styles.livePulse} />
                  <div className={styles.liveAlertMeta}>
                    <span className={styles.liveAlertTitle}>Active Call: {liveMeeting.title}</span>
                    <span className={styles.liveAlertSub}>Click to open transcription dashboard</span>
                  </div>
                  <ArrowRight size={16} className={styles.arrow} />
                </div>
              )}
            </div>

            {/* Quick Actions Strip */}
            <div className={`${styles.quickActionsStrip} glass-card`}>
              <button className={styles.actionBtn} onClick={() => setIsJoinOpen(true)}>
                <div className={`${styles.actionIcon} ${styles.iconIndigo}`}>
                  <Plus size={18} />
                </div>
                <span>Join Bot</span>
              </button>
              <button className={styles.actionBtn} onClick={() => setIsUploadOpen(true)}>
                <div className={`${styles.actionIcon} ${styles.iconEmerald}`}>
                  <Upload size={18} />
                </div>
                <span>Upload Audio</span>
              </button>
              <button className={styles.actionBtn} onClick={() => navigate("/tasks")}>
                <div className={`${styles.actionIcon} ${styles.iconAmber}`}>
                  <ListTodo size={18} />
                </div>
                <span>New Task</span>
              </button>
              <button className={styles.actionBtn} onClick={() => navigate("/chat")}>
                <div className={`${styles.actionIcon} ${styles.iconPurple}`}>
                  <MessageSquare size={18} />
                </div>
                <span>AI Chat</span>
              </button>
            </div>

            {/* KPI Strip */}
            <div className={styles.kpiStrip}>
              <StatCard
                title="Total Meetings"
                value={overview?.total_meetings ?? meetings.length}
                icon={<Calendar size={20} />}
                iconColor="indigo"
                trend={{
                  value: Math.abs(overview?.total_meetings_delta ?? 0),
                  isPositive: (overview?.total_meetings_delta ?? 0) >= 0,
                  label: "vs last month"
                }}
                sparklineData={meetingsSparkline}
              />

              <StatCard
                title="Meeting Hours"
                value={totalMeetingHours}
                formatter={(v) => `${v}h`}
                icon={<Clock size={20} />}
                iconColor="emerald"
                trend={{
                  value: Math.abs(overview?.total_hours_delta ?? 0),
                  isPositive: (overview?.total_hours_delta ?? 0) >= 0,
                  label: "vs last month"
                }}
                sparklineData={hoursSparkline}
              />

              <StatCard
                title="Open Tasks"
                value={openTasks}
                icon={<CheckSquare size={20} />}
                iconColor="amber"
                trend={{ value: overdueTasks, isPositive: overdueTasks === 0, label: `${overdueTasks} overdue` }}
                sparklineData={[openTasks, openTasks, openTasks, openTasks, openTasks, openTasks, openTasks]}
              />

              <div className={`${styles.healthProgressCard} glass-card`}>
                <div className={styles.kpiMeta}>
                  <span className={styles.kpiLabel}>Avg Meeting Health</span>
                  <span className={styles.healthVal}>{avgHealth}%</span>
                  <span className={styles.kpiSub}>vs org benchmark</span>
                </div>
                <div className={styles.progressRingWrapper}>
                  <ProgressRing value={avgHealth} size={64} strokeWidth={6} color="var(--emerald)" showValue={false} />
                </div>
              </div>
            </div>

            {/* Charts Row */}
            <div className={styles.chartsGrid}>
              <Card className={styles.chartCard}>
                <h3>Sentiment Timeline</h3>
                <p className={styles.chartSub}>Recent meeting mood tracking</p>
                <div className={styles.chartWrapper}>
                  {sentimentData.length > 0 ? (
                    <AreaChart data={sentimentData} color="var(--indigo)" />
                  ) : (
                    <div style={{ display: 'flex', height: '100%', alignItems: 'center', justifyContent: 'center', color: 'var(--text-tertiary)' }}>
                      Not enough data yet
                    </div>
                  )}
                </div>
              </Card>

              <Card className={styles.chartCard}>
                <h3>Speaking Balance</h3>
                <p className={styles.chartSub}>Talk time contribution (minutes)</p>
                <div className={styles.chartWrapper}>
                  {speakingBalanceData.length > 0 ? (
                    <BarChart data={speakingBalanceData} />
                  ) : (
                    <div style={{ display: 'flex', height: '100%', alignItems: 'center', justifyContent: 'center', color: 'var(--text-tertiary)' }}>
                      Not enough data yet
                    </div>
                  )}
                </div>
              </Card>
            </div>

            {/* Schedule & Tasks Split */}
            <div className={styles.splitGrid}>
              <Card className={styles.listCard}>
                <div className={styles.cardHeader}>
                  <h3>Recent Meetings</h3>
                  <Button variant="ghost" size="sm" onClick={() => navigate("/meetings/recordings")}>
                    View all
                  </Button>
                </div>
                <div className={styles.listContent}>
                  {meetings.length === 0 && (
                    <div style={{ padding: '1.5rem', textAlign: 'center', color: 'var(--text-tertiary)', fontSize: '0.875rem' }}>
                      No meetings yet — call the bot to start recording!
                    </div>
                  )}
                  {meetings.slice(0, 3).map((m) => (
                    <div
                      key={m.id}
                      className={styles.scheduleRow}
                      onClick={() => navigate(m.status === "joining" || m.status === "lobby" || m.status === "recording" ? `/live/${m.id}` : `/meetings/${m.id}`)}
                    >
                      <div className={styles.scheduleTime}>
                        <Clock size={14} />
                        <span>{m.started_at ? new Date(m.started_at).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }) : '—'}</span>
                      </div>
                      <div className={styles.scheduleMeta}>
                        <span className={styles.scheduleTitle}>{m.title || 'Untitled Meeting'}</span>
                        <div className={styles.rowTags}>
                          <Badge className={m.platform === 'meet' ? 'badge-emerald' : 'badge-indigo'}>{m.platform}</Badge>
                          <Badge className={m.status === 'joining' || m.status === 'lobby' || m.status === 'recording' ? 'badge-red' : m.status === 'done' ? 'badge-emerald' : 'badge-gray'}>{m.status}</Badge>
                        </div>
                      </div>
                      <ArrowRight size={14} className={styles.arrow} />
                    </div>
                  ))}
                </div>
              </Card>

              <Card className={styles.listCard}>
                <div className={styles.cardHeader}>
                  <h3>Pending Action Items</h3>
                  <Button variant="ghost" size="sm" onClick={() => navigate("/tasks")}>
                    View board
                  </Button>
                </div>
                <div className={styles.listContent}>
                  {tasks.length === 0 && (
                    <div style={{ padding: '1.5rem', textAlign: 'center', color: 'var(--text-tertiary)', fontSize: '0.875rem' }}>
                      All caught up! No pending tasks.
                    </div>
                  )}
                  {tasks.slice(0, 4).map((item) => (
                    <div key={item.id} className={styles.taskRow}>
                      <div className={styles.taskMeta}>
                        <span className={styles.taskTitle}>{item.title}</span>
                        <span className={styles.taskDate}>{item.due_date ? `Due: ${item.due_date}` : item.priority}</span>
                      </div>
                      <Avatar name={item.assignee_name || '?'} size="xs" />
                    </div>
                  ))}
                </div>
              </Card>
            </div>

            {/* Heatmap Section */}
            <ContributionGrid defaultTimeframe="month" />
          </div>

          {/* Sidebar Column */}
          <div className={styles.sidebarCol}>
            {/* Active / Last Meeting Widget */}
            <MeetingWidget liveMeeting={liveMeeting} lastMeeting={lastMeeting} />

            {/* Live Intelligence Activity Feed */}
            <div className={`${styles.intelligenceFeedCard} glass-card`}>
              <div className={styles.feedHeader}>
                <Brain size={18} className={styles.intelligenceIcon} />
                <span className={styles.feedTitle}>Intelligence Feed</span>
              </div>
              <div className={styles.feedItems}>
                {intelligenceFeed.length === 0 && (
                  <div style={{ padding: '1rem', textAlign: 'center', color: 'var(--text-tertiary)', fontSize: '0.875rem' }}>
                    Waiting for activity...
                  </div>
                )}
                {intelligenceFeed.map(item => (
                  <div key={item.id} className={styles.feedItem}>
                    <div className={`${styles.feedDot} ${styles[`dot${item.color.charAt(0).toUpperCase() + item.color.slice(1)}`]}`} />
                    <div className={styles.feedTextContainer}>
                      <p className={styles.feedText}>
                        <ReactMarkdown 
                          components={{ p: React.Fragment, strong: 'strong', em: 'em' }}
                        >
                          {item.text}
                        </ReactMarkdown>
                      </p>
                      <span className={styles.feedTime}>
                        {Math.floor((Date.now() - item.date.getTime()) / 60000) < 60 
                          ? `${Math.max(1, Math.floor((Date.now() - item.date.getTime()) / 60000))}m ago`
                          : `${Math.floor((Date.now() - item.date.getTime()) / 3600000)}h ago`}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Pro Tips / Suggestion Card */}
            <div className={`${styles.proTipCard} glass-card`}>
              <div className={styles.proTipHeader}>
                <Sparkles size={16} className={styles.proTipIcon} />
                <span>AI Meeting Tip</span>
              </div>
              <p className={styles.proTipDesc}>
                {proTip}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Join Call Modal */}
      <JoinMeetingModal isOpen={isJoinOpen} onClose={() => setIsJoinOpen(false)} />

      {/* Upload Modal */}
      <Modal isOpen={isUploadOpen} onClose={() => setIsUploadOpen(false)} title="Upload Recording">
        <form onSubmit={handleUploadSubmit} className={styles.modalForm}>
          {uploadProgress !== null ? (
            <div className={styles.uploadProgress}>
              <span>Uploading File ({uploadProgress}%)</span>
              <div className={styles.progressBar}>
                <div className={styles.progressFill} style={{ width: `${uploadProgress}%` }} />
              </div>
            </div>
          ) : (
            <div className={styles.dropZone}>
              <Upload size={32} />
              <span>Drag & Drop meeting audio or video file</span>
              <span className={styles.dropSub}>Supports MP3, MP4, WAV, WEBM up to 500MB</span>
              <input type="file" className={styles.fileInput} onChange={() => setUploadProgress(0)} />
            </div>
          )}
          <div className={styles.modalActions}>
            <Button variant="outline" type="button" onClick={() => setIsUploadOpen(false)}>
              Cancel
            </Button>
            <Button variant="primary" type="submit" disabled={uploadProgress !== null}>
              Process File
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
};
export default Dashboard;
