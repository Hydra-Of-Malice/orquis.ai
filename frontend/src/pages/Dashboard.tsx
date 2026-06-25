import React, { useState, useEffect } from "react";
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

// Countdown component for next meeting
const CountdownTimer: React.FC = () => {
  const [seconds, setSeconds] = useState(1342); // ~22 mins

  useEffect(() => {
    const timer = setInterval(() => {
      setSeconds((prev) => (prev > 0 ? prev - 1 : 0));
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;

  return (
    <div className={styles.countdownBox}>
      <div className={styles.countdownHeader}>
        <span className={styles.pulseDot} />
        <span className={styles.countdownTitle}>Upcoming Meeting</span>
      </div>
      <div className={styles.countdownVal}>
        {mins}m {secs.toString().padStart(2, "0")}s
      </div>
      <div className={styles.countdownMeta}>
        <span className={styles.countdownName}>Q3 Design & Feedback Sync</span>
        <span className={styles.countdownPlatform}>Zoom • 12 participants</span>
      </div>
    </div>
  );
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

  const { data: overview } = useQuery({
    queryKey: ['analytics-overview'],
    queryFn: () => analyticsApi.getOverview({ days: 30 }),
    retry: 1,
  });

  const { data: sentimentTrend } = useQuery({
    queryKey: ['sentiment-trend'],
    queryFn: () => analyticsApi.getSentimentTrend({ days: 7 }),
    retry: 1,
  });

  const { data: deptHours } = useQuery({
    queryKey: ['dept-hours'],
    queryFn: () => analyticsApi.getDepartmentHours(),
    retry: 1,
  });

  // ── Bot start mutation ─────────────────────────────────────────────────────
  const startBotMutation = useMutation({
    mutationFn: meetingsApi.startBot,
    onSuccess: (meeting) => {
      queryClient.invalidateQueries({ queryKey: ['meetings'] });
      setIsJoinOpen(false);
      setMeetingTitleInput('');
      setMeetingUrlInput('');
      navigate(`/live/${meeting.id}`);
    },
  });

  // ── Modals state ───────────────────────────────────────────────────────────
  const [isJoinOpen, setIsJoinOpen] = useState(false);
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [meetingTitleInput, setMeetingTitleInput] = useState("");
  const [meetingUrlInput, setMeetingUrlInput] = useState("");
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [botError, setBotError] = useState("");

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
  const liveMeeting = meetings.find((m) => m.status === "recording");
  const openTasks = taskStats?.todo ?? 0;
  const overdueTasks = taskStats?.overdue ?? 0;
  const avgHealth = overview?.avg_health_score ?? 0;

  const sentimentData = sentimentTrend?.length
    ? sentimentTrend
    : [{ name: "Mon", value: 65 }, { name: "Tue", value: 72 }, { name: "Wed", value: 68 },
       { name: "Thu", value: 80 }, { name: "Fri", value: 75 }, { name: "Sat", value: 70 }, { name: "Sun", value: 82 }];

  const speakingBalanceData = deptHours?.length
    ? deptHours.slice(0, 4)
    : [{ name: "Engineering", value: 55 }, { name: "Product", value: 30 }, { name: "Sales", value: 15 }];

  // ── Handlers ───────────────────────────────────────────────────────────────
  const handleJoinSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setBotError('');
    if (!meetingUrlInput) { setBotError('Meeting URL is required'); return; }
    startBotMutation.mutate({
      meeting_url: meetingUrlInput,
      title: meetingTitleInput || undefined,
    });
  };

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
                trend={{ value: overview?.total_meetings_delta ?? 0, isPositive: (overview?.total_meetings_delta ?? 0) >= 0, label: "vs last month" }}
                sparklineData={[1, 2, 4, 3, 2, 5, meetings.length]}
              />

              <StatCard
                title="Meeting Hours"
                value={Math.round((overview?.total_hours ?? 0) * 10) / 10}
                formatter={(v) => `${v}h`}
                icon={<Clock size={20} />}
                iconColor="emerald"
                trend={{ value: overview?.total_hours_delta ?? 0, isPositive: (overview?.total_hours_delta ?? 0) >= 0, label: "vs last month" }}
                sparklineData={[2.1, 2.8, 3.2, 3.5, 4.0, 3.8, overview?.total_hours ?? 4.2]}
              />

              <StatCard
                title="Open Tasks"
                value={openTasks}
                icon={<CheckSquare size={20} />}
                iconColor="amber"
                trend={{ value: overdueTasks, isPositive: overdueTasks === 0, label: `${overdueTasks} overdue` }}
                sparklineData={[12, 10, 8, 9, 7, 8, openTasks]}
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
                <p className={styles.chartSub}>Weekly aggregated mood tracking</p>
                <div className={styles.chartWrapper}>
                  <AreaChart data={sentimentData} color="var(--indigo)" />
                </div>
              </Card>

              <Card className={styles.chartCard}>
                <h3>Speaking Balance</h3>
                <p className={styles.chartSub}>Talk time contribution distribution</p>
                <div className={styles.chartWrapper}>
                  <BarChart data={speakingBalanceData} />
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
                      onClick={() => navigate(m.status === "recording" ? `/live/${m.id}` : `/meetings/${m.id}`)}
                    >
                      <div className={styles.scheduleTime}>
                        <Clock size={14} />
                        <span>{m.started_at ? new Date(m.started_at).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }) : '—'}</span>
                      </div>
                      <div className={styles.scheduleMeta}>
                        <span className={styles.scheduleTitle}>{m.title || 'Untitled Meeting'}</span>
                        <div className={styles.rowTags}>
                          <Badge className={m.platform === 'meet' ? 'badge-emerald' : 'badge-indigo'}>{m.platform}</Badge>
                          <Badge className={m.status === 'recording' ? 'badge-red' : m.status === 'done' ? 'badge-emerald' : 'badge-gray'}>{m.status}</Badge>
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
            {/* Upcoming Meeting Countdown */}
            <CountdownTimer />

            {/* Live Intelligence Activity Feed */}
            <div className={`${styles.intelligenceFeedCard} glass-card`}>
              <div className={styles.feedHeader}>
                <Brain size={18} className={styles.intelligenceIcon} />
                <span className={styles.feedTitle}>Intelligence Feed</span>
              </div>
              <div className={styles.feedItems}>
                <div className={styles.feedItem}>
                  <div className={`${styles.feedDot} ${styles.dotEmerald}`} />
                  <div className={styles.feedTextContainer}>
                    <p className={styles.feedText}>
                      <strong>Budget Risk</strong> detected in <em>Q3 Design Review</em> meeting.
                    </p>
                    <span className={styles.feedTime}>10m ago</span>
                  </div>
                </div>

                <div className={styles.feedItem}>
                  <div className={`${styles.feedDot} ${styles.dotIndigo}`} />
                  <div className={styles.feedTextContainer}>
                    <p className={styles.feedText}>
                      Rahul was **mentioned** by Mia regarding <em>Sprint Planning</em> deliverables.
                    </p>
                    <span className={styles.feedTime}>1h ago</span>
                  </div>
                </div>

                <div className={styles.feedItem}>
                  <div className={`${styles.feedDot} ${styles.dotAmber}`} />
                  <div className={styles.feedTextContainer}>
                    <p className={styles.feedText}>
                      Action item <em>"Submit wireframe concepts"</em> sync'd to <strong>Linear</strong>.
                    </p>
                    <span className={styles.feedTime}>3h ago</span>
                  </div>
                </div>

                <div className={styles.feedItem}>
                  <div className={`${styles.feedDot} ${styles.dotPurple}`} />
                  <div className={styles.feedTextContainer}>
                    <p className={styles.feedText}>
                      Weekly summary draft compiled and emailed to the <strong>Engineering Team</strong>.
                    </p>
                    <span className={styles.feedTime}>5h ago</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Pro Tips / Suggestion Card */}
            <div className={`${styles.proTipCard} glass-card`}>
              <div className={styles.proTipHeader}>
                <Sparkles size={16} className={styles.proTipIcon} />
                <span>AI Meeting Tip</span>
              </div>
              <p className={styles.proTipDesc}>
                Your average speaking monologue is 3.5 minutes. Try asking open-ended questions like "Mia, what are your thoughts?" to increase team engagement by 15%.
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Join Call Modal */}
      <Modal isOpen={isJoinOpen} onClose={() => { setIsJoinOpen(false); setBotError(''); }} title="Join Meeting & Call Bot">
        <form onSubmit={handleJoinSubmit} className={styles.modalForm}>
          <div className={styles.formGroup}>
            <label>Meeting Title <span style={{ color: 'var(--text-tertiary)', fontWeight: 400 }}>(optional)</span></label>
            <Input
              placeholder="e.g. Q3 Design Review"
              value={meetingTitleInput}
              onChange={(e) => setMeetingTitleInput(e.target.value)}
            />
          </div>
          <div className={styles.formGroup}>
            <label>Meeting URL <span style={{ color: 'var(--rose)', fontSize: '0.75rem' }}>*</span></label>
            <Input
              required
              placeholder="https://meet.google.com/xxx-yyyy-zzz"
              value={meetingUrlInput}
              onChange={(e) => { setMeetingUrlInput(e.target.value); setBotError(''); }}
            />
            <span style={{ fontSize: '0.75rem', color: 'var(--text-tertiary)', marginTop: '0.25rem', display: 'block' }}>Supports Google Meet and Microsoft Teams</span>
          </div>
          {botError && (
            <div style={{ color: 'var(--rose)', fontSize: '0.8125rem', marginBottom: '0.5rem' }}>{botError}</div>
          )}
          {startBotMutation.error && (
            <div style={{ color: 'var(--rose)', fontSize: '0.8125rem', marginBottom: '0.5rem' }}>
              {(startBotMutation.error as any)?.response?.data?.detail || 'Failed to start bot'}
            </div>
          )}
          <div className={styles.modalActions}>
            <Button variant="outline" type="button" onClick={() => setIsJoinOpen(false)} disabled={startBotMutation.isPending}>
              Cancel
            </Button>
            <Button variant="primary" type="submit" disabled={startBotMutation.isPending}
              icon={startBotMutation.isPending ? <Loader2 size={14} className="spin" /> : undefined}>
              {startBotMutation.isPending ? 'Calling Bot...' : 'Call Zapper Bot'}
            </Button>
          </div>
        </form>
      </Modal>

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
