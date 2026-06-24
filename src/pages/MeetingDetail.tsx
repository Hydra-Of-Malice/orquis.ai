import React, { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { meetingsApi } from "../services/meetings";
import { tasksApi } from "../services/tasks";
import { PageHeader } from "../components/layout/PageHeader";
import { Card } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { Avatar } from "../components/ui/Avatar";
import { Badge } from "../components/ui/Badge";
import { Tabs } from "../components/ui/Tabs";
import { Input } from "../components/ui/Input";
import { RadarChart } from "../components/charts/RadarChart";
import { DonutChart } from "../components/charts/DonutChart";
import { AreaChart } from "../components/charts/AreaChart";
import { ProgressRing } from "../components/ui/ProgressRing";
import {
  ArrowLeft,
  CheckCircle,
  AlertTriangle,
  HelpCircle,
  Tag,
  Search,
  Download,
  Share2,
  CheckSquare,
  Clock,
  Play,
  Pause,
  Check,
  ExternalLink,
  Plus,
  Copy,
  ChevronDown,
  ChevronUp,
  Volume2,
  Lock,
  ListTodo,
  FileText,
  MessageSquare,
  Sparkles
} from "lucide-react";
import styles from "./MeetingDetail.module.css";
import clsx from "clsx";

export const MeetingDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: dbMeeting, isLoading: isMeetingLoading } = useQuery({
    queryKey: ["meeting", id],
    queryFn: () => meetingsApi.get(id!),
    enabled: !!id,
    retry: 1,
  });

  const { data: dbTranscript = [], isLoading: isTranscriptLoading } = useQuery({
    queryKey: ["meeting-transcript", id],
    queryFn: () => meetingsApi.getTranscript(id!),
    enabled: !!id,
    retry: 1,
  });

  const { data: dbActionItems = [], isLoading: isTasksLoading } = useQuery({
    queryKey: ["meeting-tasks", id],
    queryFn: () => tasksApi.list({ meeting_id: id }),
    enabled: !!id,
    retry: 1,
  });

  const meeting = dbMeeting ? {
    id: dbMeeting.id,
    title: dbMeeting.title || "Untitled Meeting",
    meetingType: (dbMeeting.platform || "meet") as "meet" | "teams" | "zoom" | "webex" | "uploaded",
    startedAt: dbMeeting.started_at || new Date().toISOString(),
    endedAt: dbMeeting.ended_at,
    durationSeconds: dbMeeting.duration_seconds || 270,
    status: dbMeeting.status === "done" ? "completed" : dbMeeting.status,
    healthScore: dbMeeting.health_score || 88,
    engagementScore: dbMeeting.engagement_score || 85,
    sentiment: dbMeeting.sentiment || "productive",
    participantNames: dbMeeting.participant_names || [],
    participantCount: dbMeeting.participant_count || 0,
    summaryMd: dbMeeting.summary_md || "",
    summaryJson: (dbMeeting.summary_json || {}) as any,
    analytics: (dbMeeting as any).analytics || null,
  } : {
    id: id || "mock",
    title: "Loading Meeting...",
    meetingType: "meet" as "meet" | "teams" | "zoom" | "webex" | "uploaded",
    startedAt: new Date().toISOString(),
    durationSeconds: 270,
    status: "completed" as const,
    healthScore: 88,
    engagementScore: 85,
    sentiment: "productive",
    participantNames: [],
    participantCount: 0,
    summaryMd: "",
    summaryJson: {} as any,
    analytics: null as any,
  };

  const addActionItemMutation = useMutation({
    mutationFn: tasksApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["meeting-tasks", id] });
    },
  });

  const updateActionItemMutation = useMutation({
    mutationFn: ({ taskId, data }: { taskId: string; data: any }) => tasksApi.update(taskId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["meeting-tasks", id] });
    },
  });

  const [activeTab, setActiveTab] = useState("summary");
  const [summaryType, setSummaryType] = useState<"executive" | "technical" | "sales">("technical");
  const [transcriptSearch, setTranscriptSearch] = useState("");
  const [speakerFilter, setSpeakerFilter] = useState("all");
  
  // Audio playback mockup state
  const [isPlaying, setIsPlaying] = useState(false);
  const [audioProgress, setAudioProgress] = useState(0); // in seconds
  const totalAudioDuration = meeting.durationSeconds;

  useEffect(() => {
    let interval: any;
    if (isPlaying) {
      interval = setInterval(() => {
        setAudioProgress((prev) => {
          if (prev >= totalAudioDuration) {
            setIsPlaying(false);
            return 0;
          }
          return prev + 1;
        });
      }, 1000);
    }
    return () => clearInterval(interval);
  }, [isPlaying, totalAudioDuration]);

  const handleAudioScrub = (e: React.ChangeEvent<HTMLInputElement>) => {
    setAudioProgress(parseInt(e.target.value));
  };

  const jumpToTime = (timeStr: string) => {
    const parts = timeStr.split(":");
    const seconds = parseInt(parts[0]) * 60 + parseInt(parts[1]);
    setAudioProgress(seconds);
    setIsPlaying(true);
    
    // Switch to transcript tab if not there
    setActiveTab("transcript");
  };

  const formatAudioTime = (secs: number) => {
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return `${m}:${s.toString().padStart(2, "0")}`;
  };

  // Typing TLDR animation
  const [typedSummary, setTypedSummary] = useState("");
  const fullTechnicalSummary = meeting.summaryMd || "The engineering team evaluated Faster-Whisper v3 and decided to adopt it for production, yielding a 15% WER improvement. To prevent HTTP server timeout issues, audio chunks will be ingested via Redis Streams. GPU VRAM limits and concurrency loading benchmarks are scheduled for review on Thursday.";
  const fullExecutiveSummary = meeting.summaryJson?.short_summary || "Adopted Faster-Whisper v3 for live meeting transcription and Redis Streams to buffer client ingestion. Next sync scheduled for Thursday to evaluate VRAM requirements.";
  const fullSalesSummary = meeting.summaryJson?.overview || "Identified core architecture blockers (ingestion timeout issues) and implemented structural fixes (Redis Streams) to secure beta stability for client sync. Value proposition: 15% accuracy gains.";

  const getSummaryText = () => {
    if (summaryType === "technical") return fullTechnicalSummary;
    if (summaryType === "executive") return fullExecutiveSummary;
    return fullSalesSummary;
  };

  useEffect(() => {
    setTypedSummary("");
    const targetText = getSummaryText();
    let index = 0;
    const typingSpeed = 10; // ms
    const timer = setInterval(() => {
      setTypedSummary(targetText.slice(0, index + 1));
      index++;
      if (index >= targetText.length) {
        clearInterval(timer);
      }
    }, typingSpeed);
    return () => clearInterval(timer);
  }, [summaryType, activeTab, typedSummary === ""]); // Re-run if summaryType changes or activeTab switches

  // Selected topic tag for highlighting/filtering transcript
  const [selectedTopic, setSelectedTopic] = useState<string | null>(null);

  // New Action Item state
  const [newActionItemTitle, setNewActionItemTitle] = useState("");
  const [newActionItemAssignee, setNewActionItemAssignee] = useState("Mia Wong");
  const [newActionItemPriority, setNewActionItemPriority] = useState<"low" | "medium" | "high" | "urgent">("medium");

  // Accordion details for Coaching Tips
  const [expandedTip, setExpandedTip] = useState<string | null>(null);

  // Copy-to-clipboard state
  const [copiedSegmentId, setCopiedSegmentId] = useState<string | null>(null);

  const handleCopySegment = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedSegmentId(id);
    setTimeout(() => setCopiedSegmentId(null), 1500);
  };

  // Tabs structure
  const tabItems = [
    { id: "summary", label: "Summary", icon: <FileText size={14} /> },
    { id: "transcript", label: "Transcript", icon: <MessageSquare size={14} /> },
    { id: "action_items", label: "Action Items", icon: <CheckSquare size={14} /> },
    { id: "analytics", label: "Analytics", icon: <BarChartIcon size={14} /> },
  ];

  const formatTimeMs = (ms: number) => {
    const mins = Math.floor(ms / 60000);
    const secs = Math.floor((ms % 60000) / 1000);
    return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  };

  const meetingActionItems = dbActionItems.map((item: any) => ({
    id: item.id,
    meetingId: item.meeting_id,
    title: item.title,
    description: item.description,
    assigneeName: item.assignee_name || "Unassigned",
    priority: item.priority || "medium",
    status: item.status === "todo" ? "pending" : item.status,
    dueDate: item.due_date,
  }));

  const mockDecisions = [
    { id: "dec_1", title: "Adopt Faster-Whisper v3 for production live transcription pipeline" },
    { id: "dec_2", title: "Buffer audio ingestion directly in Redis Streams to eliminate server timeouts" },
    { id: "dec_3", title: "Schedule final benchmark review for Thursday, June 25th" },
  ];

  const mockRisks = [
    { id: "risk_1", title: "Whisper v3 latency might exceed 2-second live SLA under concurrent worker stream loads", detail: "Mitigation: Evaluating celery worker clusters and GPU memory thresholds." },
    { id: "risk_2", title: "HTTP connection drops on large file uploads", detail: "Mitigation: Added chunked upload logic in settings." }
  ];

  const [expandedRisk, setExpandedRisk] = useState<string | null>(null);

  const mockQuestions = [
    { id: "q_1", asker: "Jay Shah", text: "Do we have enough GPU VRAM to support multiple concurrent streams under load?", answered: true, answer: "Mia Wong is running benchmarks to document VRAM usage thresholds by Thursday." },
    { id: "q_2", asker: "Rahul Patel", text: "Can we roll this out to beta by July 15th?", answered: true, answer: "Yes, assuming the Redis audio streams cluster setup is deployed next week." }
  ];

  const mockSegments = [
    { id: "seg_1", speakerName: "Rahul Patel", start: "00:00", text: "Thanks everyone for joining today's engineering sync. We have a couple of big topics. First off is benchmarking Faster-Whisper v3 for our live transcription backend, and second is moving our audio ingestion to Redis Streams." },
    { id: "seg_2", speakerName: "Mia Wong", start: "00:16", text: "Yeah, I've run the initial benchmarks. Faster-Whisper v3 is giving us about a 15% reduction in word error rate, especially in noisy audio or with overlapping speakers. I think we should definitely adopt it for production." },
    { id: "seg_3", speakerName: "Jay Shah", start: "00:33", text: "What about the latency overhead? Do we have enough GPU VRAM to support multiple concurrent streams under load?" },
    { id: "seg_4", speakerName: "Rahul Patel", start: "00:45", text: "That's a key risk. Mia, can you benchmark Faster-Whisper under concurrent stream load by Thursday? We need to make sure we don't exceed our 2-second live lag SLA. I can help set up the k6 loading environment." },
    { id: "seg_5", speakerName: "Mia Wong", start: "01:03", text: "Sure, I'll take that task. I'll document the VRAM usage and error rate thresholds across different worker sizes." },
    { id: "seg_6", speakerName: "Jay Shah", start: "01:13", text: "Perfect. On the second topic, I've sketched out the Redis Streams setup. It will buffer audio chunks directly from the bot service and feed the transcription celery tasks. It should eliminate our occasional HTTP timeout issues." },
    { id: "seg_7", speakerName: "Rahul Patel", start: "01:33", text: "Excellent. Let's make the decision to use Redis Streams for the audio pipeline. Jay, please set up the initial pgvector indexes and Redis cluster configuration by next Tuesday, so we can launch our beta by July 15th." },
  ];

  // Dynamic values loaded from summary_json if present
  const decisions = (meeting.summaryJson?.decisions || []).length > 0
    ? (meeting.summaryJson.decisions as string[]).map((d, idx) => ({ id: `dec_${idx}`, title: d }))
    : mockDecisions;

  const risks = (meeting.summaryJson?.risks || []).length > 0
    ? (meeting.summaryJson.risks as string[]).map((r, idx) => ({ id: `risk_${idx}`, title: r, detail: "Identified during summary extraction." }))
    : mockRisks;

  const questions = (meeting.summaryJson?.questions || []).length > 0
    ? (meeting.summaryJson.questions as string[]).map((q, idx) => ({ id: `q_${idx}`, asker: "Participant", text: q, answered: false, answer: "" }))
    : mockQuestions;

  const segments = dbTranscript.length > 0
    ? dbTranscript.map((s: any) => ({
        id: s.id,
        speakerName: s.speaker_name || "Unknown Speaker",
        start: formatTimeMs(s.start_ms || 0),
        text: s.text || "",
      }))
    : mockSegments;

  // Map speakers to colors for timelines
  const getSpeakerColorClass = (name: string) => {
    if (name === "Rahul Patel") return styles.speakerRahul;
    if (name === "Mia Wong") return styles.speakerMia;
    return styles.speakerJay;
  };

  const handleAddActionItem = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newActionItemTitle) return;
    addActionItemMutation.mutate({
      title: newActionItemTitle,
      assignee_name: newActionItemAssignee,
      priority: newActionItemPriority,
      status: "todo",
      meeting_id: id,
    });
    setNewActionItemTitle("");
  };

  const updateActionItemStatus = (taskId: string, targetStatus: "todo" | "in_progress" | "done") => {
    updateActionItemMutation.mutate({
      taskId,
      data: { status: targetStatus },
    });
  };

  // Analytics mapping
  const analyticsData = meeting.analytics;
  const talkTimeMap = analyticsData?.talk_time_per_speaker || {};
  const hasTalkTime = Object.keys(talkTimeMap).length > 0;

  const donutData = hasTalkTime
    ? Object.entries(talkTimeMap).map(([name, val]: any) => ({
        name,
        value: Math.round(val),
      }))
    : [
        { name: "Rahul Patel", value: 55 },
        { name: "Mia Wong", value: 30 },
        { name: "Jay Shah", value: 15 },
      ];

  const speakerStatsRows = hasTalkTime
    ? Object.entries(talkTimeMap).map(([name, val]: any) => ({
        name,
        pct: `${Math.round(val)}%`,
        wpm: 140,
        questions: 0,
        overlaps: 0,
      }))
    : [
        { name: "Rahul Patel", pct: "55%", wpm: 145, questions: 0, overlaps: 0 },
        { name: "Mia Wong", pct: "30%", wpm: 152, questions: 0, overlaps: 1 },
        { name: "Jay Shah", pct: "15%", wpm: 138, questions: 1, overlaps: 1 },
      ];

  const sentimentTimeline = analyticsData?.sentiment_timeline || [];
  const sentimentChartData = sentimentTimeline.length > 0
    ? sentimentTimeline.map((item: any) => ({
        name: `${item.minute}m`,
        value: Math.round((item.score + 1) * 50),
      }))
    : [
        { name: "0m", value: 65 },
        { name: "10m", value: 70 },
        { name: "20m", value: 60 },
        { name: "30m", value: 85 },
        { name: "40m", value: 90 },
      ];

  const highlightKeyword = (text: string, keyword: string) => {
    if (!keyword) return text;
    const parts = text.split(new RegExp(`(${keyword})`, "gi"));
    return (
      <>
        {parts.map((part, i) =>
          part.toLowerCase() === keyword.toLowerCase() ? (
            <mark key={i} className={styles.highlight}>
              {part}
            </mark>
          ) : (
            part
          )
        )}
      </>
    );
  };

  return (
    <div className={styles.container}>
      <PageHeader
        breadcrumbs={["Meetings", meeting.title]}
        actions={
          <div className={styles.headerActions}>
            <Button variant="outline" size="sm" icon={<Share2 size={16} />}>
              Share
            </Button>
            <Button variant="outline" size="sm" icon={<Download size={16} />}>
              Export Summary
            </Button>
          </div>
        }
      />

      {/* Back link */}
      <div className={styles.backRow}>
        <button className={styles.backBtn} onClick={() => navigate("/meetings/recordings")}>
          <ArrowLeft size={16} />
          <span>Back to Recordings</span>
        </button>
      </div>

      {/* Enhanced Hero header */}
      <div className={`${styles.heroHeader} glass-card`}>
        <div className={styles.heroTop}>
          <div className={styles.heroMain}>
            <div className={styles.heroTitleRow}>
              <h2>{meeting.title}</h2>
              <Badge className={`badge-${meeting.meetingType === "zoom" ? "indigo" : meeting.meetingType === "meet" ? "emerald" : "purple"}`}>
                {meeting.meetingType}
              </Badge>
            </div>
            <div className={styles.heroMetaDetails}>
              <span className={styles.metaSpan}>
                <Clock size={12} />
                {new Date(meeting.startedAt).toLocaleDateString(undefined, {
                  weekday: "long",
                  month: "short",
                  day: "numeric",
                })}
              </span>
              <span className={styles.metaDivider}>•</span>
              <span className={styles.metaSpan}>45 mins duration</span>
              <span className={styles.metaDivider}>•</span>
              <span className={styles.metaSpan}>{meetingActionItems.length} action items</span>
            </div>
          </div>

          <div className={styles.heroMetrics}>
            <div className={styles.avatarsStack}>
              <div className={styles.avatarsWrapper}>
                <Avatar name="Rahul Patel" size="sm" />
                <Avatar name="Mia Wong" size="sm" />
                <Avatar name="Jay Shah" size="sm" />
              </div>
              <span className={styles.avatarsLabel}>3 participants</span>
            </div>
            
            {meeting.healthScore && (
              <div className={styles.healthHeader}>
                <ProgressRing value={meeting.healthScore} size={48} strokeWidth={4.5} color="var(--emerald)" showValue={true} />
                <div className={styles.healthLabelGroup}>
                  <span className={styles.healthTitle}>Health Score</span>
                  <span className={styles.healthSub}>High engagement</span>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Audio Scrubber Mockup */}
        <div className={styles.audioPlayer}>
          <button className={styles.playPauseBtn} onClick={() => setIsPlaying(!isPlaying)}>
            {isPlaying ? <Pause size={18} fill="currentColor" /> : <Play size={18} fill="currentColor" />}
          </button>
          
          <div className={styles.playerMeta}>
            <Volume2 size={14} className={styles.volumeIcon} />
            <span className={styles.currentTime}>{formatAudioTime(audioProgress)}</span>
          </div>

          <input
            type="range"
            min="0"
            max={totalAudioDuration}
            value={audioProgress}
            onChange={handleAudioScrub}
            className={styles.scrubber}
          />

          <span className={styles.totalTime}>{formatAudioTime(totalAudioDuration)}</span>
        </div>
      </div>

      <div className={styles.tabsWrapper}>
        <Tabs items={tabItems} activeId={activeTab} onChange={setActiveTab} />
      </div>

      <div className={styles.content}>
        {/* ================= SUMMARY TAB ================= */}
        {activeTab === "summary" && (
          <div className={styles.summaryTab}>
            <div className={styles.summaryLeft}>
              <Card className={`${styles.tldrCard} glass-card`}>
                <div className={styles.tldrHeader}>
                  <div className={styles.tldrTitle}>
                    <Sparkles size={16} className={styles.sparkleIcon} />
                    <h3>AI Executive Summary</h3>
                  </div>
                  <select
                    className={styles.summarySelector}
                    value={summaryType}
                    onChange={(e) => setSummaryType(e.target.value as any)}
                  >
                    <option value="technical">Technical Summary</option>
                    <option value="executive">Executive Summary</option>
                    <option value="sales">Sales Strategy</option>
                  </select>
                </div>
                <p className={styles.typedText}>
                  {typedSummary}
                  <span className={styles.typingCursor}>|</span>
                </p>
              </Card>

              <Card className={styles.decisionsCard}>
                <h3>
                  <CheckCircle size={16} className={styles.checkIcon} />
                  Decisions Reached ({decisions.length})
                </h3>
                <div className={styles.decisionsList}>
                  {decisions.map((dec) => (
                    <div key={dec.id} className={styles.decisionRow}>
                      <span className={styles.bulletCheck}><Check size={10} /></span>
                      <p>{dec.title}</p>
                    </div>
                  ))}
                </div>
              </Card>

              <Card className={styles.risksCard}>
                <h3>
                  <AlertTriangle size={16} className={styles.riskIcon} />
                  Blockers & Actionable Risks ({risks.length})
                </h3>
                <div className={styles.risksList}>
                  {risks.map((risk) => (
                    <div key={risk.id} className={styles.riskItem}>
                      <div className={styles.riskHeader} onClick={() => setExpandedRisk(expandedRisk === risk.id ? null : risk.id)}>
                        <div className={styles.riskTitleGroup}>
                          <span className={styles.bulletRisk} />
                          <p className={styles.riskTitle}>{risk.title}</p>
                        </div>
                        {expandedRisk === risk.id ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                      </div>
                      {expandedRisk === risk.id && (
                        <div className={styles.riskDetail}>
                          <p>{risk.detail}</p>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </Card>
            </div>

            <div className={styles.summaryRight}>
              <Card className={styles.summaryRightCard}>
                <h3>Questions Asked</h3>
                <div className={styles.questionsList}>
                  {questions.map((q) => (
                    <div key={q.id} className={styles.questionBlock}>
                      <div className={styles.questionAsk}>
                        <HelpCircle size={14} className={styles.qIcon} />
                        <strong>{q.asker}:</strong>
                        <span>{q.text}</span>
                      </div>
                      {q.answered && (
                        <div className={styles.questionAns}>
                          <span className={styles.ansText}>{q.answer}</span>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </Card>

              <Card className={styles.summaryRightCard}>
                <h3>Key Topics</h3>
                <p className={styles.topicInstruction}>Click a topic to filter/highlight in the transcript</p>
                <div className={styles.topicsGrid}>
                  {["Faster-Whisper v3", "Redis Streams", "pgvector index", "Beta Release", "VRAM concurrency", "HTTP timeouts"].map((topic) => (
                    <span
                      key={topic}
                      className={clsx(styles.topicTag, selectedTopic === topic && styles.topicTagActive)}
                      onClick={() => {
                        setSelectedTopic(selectedTopic === topic ? null : topic);
                        setActiveTab("transcript");
                        if (selectedTopic !== topic) {
                          setTranscriptSearch(topic);
                        } else {
                          setTranscriptSearch("");
                        }
                      }}
                    >
                      <Tag size={11} />
                      {topic}
                    </span>
                  ))}
                </div>
              </Card>
            </div>
          </div>
        )}

        {/* ================= TRANSCRIPT TAB ================= */}
        {activeTab === "transcript" && (
          <div className={styles.transcriptTab}>
            <div className={`${styles.transcriptFilters} glass-card`}>
              <div className={styles.transcriptSearchInput}>
                <Input
                  placeholder="Search keywords or topics in transcript..."
                  icon={<Search size={16} />}
                  value={transcriptSearch}
                  onChange={(e) => setTranscriptSearch(e.target.value)}
                />
                {transcriptSearch && (
                  <button className={styles.clearSearchBtn} onClick={() => { setTranscriptSearch(""); setSelectedTopic(null); }}>
                    Clear
                  </button>
                )}
              </div>
              <select
                className={styles.speakerDropdown}
                value={speakerFilter}
                onChange={(e) => setSpeakerFilter(e.target.value)}
              >
                <option value="all">All Speakers</option>
                <option value="Rahul Patel">Rahul Patel</option>
                <option value="Mia Wong">Mia Wong</option>
                <option value="Jay Shah">Jay Shah</option>
              </select>
            </div>

            <div className={styles.timelineWrapper}>
              <div className={styles.timelineLine} />
              <div className={styles.segmentsList}>
                {segments
                  .filter(
                    (seg) =>
                      (speakerFilter === "all" || seg.speakerName === speakerFilter) &&
                      seg.text.toLowerCase().includes(transcriptSearch.toLowerCase())
                  )
                  .map((seg) => (
                    <div key={seg.id} className={clsx(styles.segmentRow, getSpeakerColorClass(seg.speakerName))}>
                      {/* Avatar timeline node */}
                      <div className={styles.timelineNode}>
                        <Avatar name={seg.speakerName} size="sm" />
                      </div>

                      <div className={`${styles.segmentContent} glass-card`}>
                        <div className={styles.segmentSpeakerHeader}>
                          <span className={styles.speakerName}>{seg.speakerName}</span>
                          <div className={styles.segmentMetaActions}>
                            <button
                              className={styles.jumpTimeBtn}
                              onClick={() => jumpToTime(seg.start)}
                              title="Jump audio playhead to here"
                            >
                              <Play size={10} className={styles.playIcon} />
                              {seg.start}
                            </button>
                            <button
                              className={styles.copyTextBtn}
                              onClick={() => handleCopySegment(seg.text, seg.id)}
                              title="Copy quote"
                            >
                              {copiedSegmentId === seg.id ? <Check size={12} className={styles.emeraldCopy} /> : <Copy size={12} />}
                            </button>
                          </div>
                        </div>
                        <div className={styles.segmentText}>
                          <p>{highlightKeyword(seg.text, transcriptSearch)}</p>
                        </div>
                      </div>
                    </div>
                  ))}
              </div>
            </div>
          </div>
        )}

        {/* ================= ACTION ITEMS TAB ================= */}
        {activeTab === "action_items" && (
          <div className={styles.actionsTab}>
            {/* Kanban Columns */}
            <div className={styles.kanbanBoard}>
              {(["pending", "in_progress", "done"] as const).map((col) => (
                <div key={col} className={styles.kanbanColumn}>
                  <div className={styles.kanbanHeader}>
                    <h4>{col === "pending" ? "Todo" : col === "in_progress" ? "In Progress" : "Done"}</h4>
                    <span className={styles.kanbanCount}>
                      {meetingActionItems.filter((i) => i.status === col).length}
                    </span>
                  </div>

                  <div className={styles.kanbanCards}>
                    {meetingActionItems
                      .filter((i) => i.status === col)
                      .map((item) => (
                        <Card key={item.id} className={clsx(styles.kanbanCard, styles[`border-${item.priority}`])}>
                          <div className={styles.kCardTop}>
                            <span className={clsx(styles.priorityBadge, styles[item.priority])}>
                              {item.priority}
                            </span>
                            <span className={styles.kCardTitle}>{item.title}</span>
                          </div>
                          
                          <div className={styles.kCardMid}>
                            {item.dueDate && (
                              <span className={clsx(styles.dueDateBadge, new Date(item.dueDate) < new Date() && styles.overdueBadge)}>
                                <Clock size={10} />
                                {item.dueDate}
                              </span>
                            )}
                          </div>

                          <div className={styles.kCardBottom}>
                            <Avatar name={item.assigneeName} size="xs" />
                            <div className={styles.kCardMeta}>
                              <span className={styles.assignee}>{item.assigneeName}</span>
                              <div className={styles.statusDropdownActions}>
                                {col !== "done" && (
                                  <button
                                    className={styles.doneBtn}
                                    onClick={() => updateActionItemStatus(item.id, col === "pending" ? "in_progress" : "done")}
                                  >
                                    {col === "pending" ? "Start" : "Resolve"}
                                  </button>
                                )}
                                {col === "done" && (
                                  <span className={styles.completedCheck}>
                                    <Check size={12} /> Closed
                                  </span>
                                )}
                              </div>
                            </div>
                          </div>
                          
                          <div className={styles.syncBadges}>
                            <span className={styles.syncBadge} title="Jira Sync Active">
                              Jira ✓
                            </span>
                            <span className={styles.syncBadge} title="Linear Sync Active">
                              Linear ✓
                            </span>
                          </div>
                        </Card>
                      ))}

                    {col === "pending" && (
                      <form onSubmit={handleAddActionItem} className={`${styles.quickAddForm} glass-card`}>
                        <input
                          type="text"
                          required
                          placeholder="+ Add Action Item..."
                          value={newActionItemTitle}
                          onChange={(e) => setNewActionItemTitle(e.target.value)}
                          className={styles.quickAddInput}
                        />
                        {newActionItemTitle && (
                          <div className={styles.quickAddMeta}>
                            <div className={styles.quickSelectsGroup}>
                              <select
                                value={newActionItemAssignee}
                                onChange={(e) => setNewActionItemAssignee(e.target.value)}
                                className={styles.quickAddAssignee}
                              >
                                <option value="Mia Wong">Mia Wong</option>
                                <option value="Jay Shah">Jay Shah</option>
                                <option value="Rahul Patel">Rahul Patel</option>
                              </select>
                              <select
                                value={newActionItemPriority}
                                onChange={(e) => setNewActionItemPriority(e.target.value as any)}
                                className={styles.quickAddAssignee}
                              >
                                <option value="low">Low Priority</option>
                                <option value="medium">Medium</option>
                                <option value="high">High</option>
                                <option value="urgent">Urgent</option>
                              </select>
                            </div>
                            <Button type="submit" size="sm" variant="primary">Add</Button>
                          </div>
                        )}
                      </form>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ================= ANALYTICS TAB ================= */}
        {activeTab === "analytics" && (
          <div className={styles.analyticsTab}>
            <div className={styles.analyticsLeft}>
              <Card className={styles.scoreCard}>
                <div className={styles.metricWidget}>
                  <div className={styles.metricVal}>88%</div>
                  <div className={styles.metricLabel}>Meeting Health Index</div>
                  <p className={styles.metricDesc}>Engagement, participation balance, and focus signals compiled by Zapper AI.</p>
                </div>
                <div className={styles.radarWrapper}>
                  <RadarChart
                    data={[
                      { subject: "Engagement", value: 85, fullMark: 100 },
                      { subject: "Speaking Balance", value: 72, fullMark: 100 },
                      { subject: "Clarity", value: 90, fullMark: 100 },
                      { subject: "Focus", value: 92, fullMark: 100 },
                      { subject: "Sentiment", value: 88, fullMark: 100 },
                      { subject: "Participation", value: 80, fullMark: 100 },
                    ]}
                  />
                </div>
              </Card>

              {/* Coaching exercises with collapsible details */}
              <Card className={styles.coachingCard}>
                <div className={styles.coachingHeader}>
                  <div className={styles.tipHeaderTitle}>
                    <Sparkles size={16} className={styles.sparkleIcon} />
                    <h3>💡 Private Leadership Coach</h3>
                  </div>
                  <Badge className="badge-gray">
                    <Lock size={10} /> Private to you
                  </Badge>
                </div>
                
                <div className={styles.coachingTips}>
                  <div className={styles.expandableTipCard}>
                    <div className={styles.tipTitleRow} onClick={() => setExpandedTip(expandedTip === "pace" ? null : "pace")}>
                      <span>1. Speaking Pace Control</span>
                      {expandedTip === "pace" ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                    </div>
                    {expandedTip === "pace" && (
                      <p className={styles.tipDetailText}>
                        Your speaking pace averaged 145 words per minute, which is inside the optimal 130-160 WPM executive range. Ensure you pause before transitions.
                      </p>
                    )}
                  </div>

                  <div className={styles.expandableTipCard}>
                    <div className={styles.tipTitleRow} onClick={() => setExpandedTip(expandedTip === "monologue" ? null : "monologue")}>
                      <span>2. Monologue Blocker Triggered</span>
                      {expandedTip === "monologue" ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                    </div>
                    {expandedTip === "monologue" && (
                      <p className={styles.tipDetailText}>
                        You had a monologue lasting 3 mins 15s at minute 12:30. Zapper detected speech dominance. In your next sync, pause every 2 mins to solicit team feedback.
                      </p>
                    )}
                  </div>

                  <div className={styles.expandableTipCard}>
                    <div className={styles.tipTitleRow} onClick={() => setExpandedTip(expandedTip === "fillers" ? null : "fillers")}>
                      <span>3. Filler Words Distribution</span>
                      {expandedTip === "fillers" ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                    </div>
                    {expandedTip === "fillers" && (
                      <p className={styles.tipDetailText}>
                        You used "like" and "um" 12 times. This is 15% lower than last week. Practice centering pauses instead of saying "so...".
                      </p>
                    )}
                  </div>
                </div>
              </Card>
            </div>

            <div className={styles.analyticsRight}>
              <Card className={styles.speakerStatsCard}>
                <h3>Speaker Breakdown</h3>
                <div className={styles.donutWrapper}>
                  <DonutChart
                    data={donutData}
                  />
                </div>
                
                <table className={styles.statsTable}>
                  <thead>
                    <tr>
                      <th>Speaker</th>
                      <th>Talk %</th>
                      <th>WPM</th>
                      <th>Questions</th>
                      <th>Overlaps</th>
                    </tr>
                  </thead>
                  <tbody>
                    {speakerStatsRows.map((row, idx) => (
                      <tr key={idx}>
                        <td>{row.name}</td>
                        <td>{row.pct}</td>
                        <td>{row.wpm}</td>
                        <td>{row.questions}</td>
                        <td>{row.overlaps}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Card>

              {/* Sentiment Timeline mini area chart */}
              <Card className={styles.sentimentCard}>
                <h3>Sentiment Progression</h3>
                <p className={styles.chartSubText}>Mood fluctuations during the sync</p>
                <div className={styles.sentimentChartWrapper}>
                  <AreaChart
                    data={sentimentChartData}
                    color="var(--emerald)"
                  />
                </div>
              </Card>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

// BarChart icon wrapper
const BarChartIcon = ({ size }: { size: number }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <line x1="18" y1="20" x2="18" y2="10" />
    <line x1="12" y1="20" x2="12" y2="4" />
    <line x1="6" y1="20" x2="6" y2="14" />
  </svg>
);

export default MeetingDetail;
