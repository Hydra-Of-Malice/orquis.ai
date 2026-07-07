import React, { useState, useEffect, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation } from "@tanstack/react-query";
import { meetingsApi } from "../services/meetings";
import { useWebSocket } from "../services/websocket";
import type { LiveEvent } from "../services/websocket";
import { Card } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { Avatar } from "../components/ui/Avatar";
import { Badge } from "../components/ui/Badge";
import { Input } from "../components/ui/Input";
import { AreaChart } from "../components/charts/AreaChart";
import {
  Video,
  Users,
  CheckSquare,
  MessageSquare,
  Play,
  PlayCircle,
  Send,
  AlertCircle,
  Clock,
  Mic,
  MicOff,
  Camera,
  CameraOff,
  Monitor,
  PhoneOff,
  Brain,
  Sparkles,
  Activity,
  Plus,
  Save,
  Check
} from "lucide-react";
import styles from "./LiveMeeting.module.css";
import clsx from "clsx";

export const LiveMeeting: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const { data: dbMeeting } = useQuery({
    queryKey: ["meeting", id],
    queryFn: () => meetingsApi.get(id!),
    enabled: !!id,
    refetchInterval: 5000,
  });

  const stopBotMutation = useMutation({
    mutationFn: () => meetingsApi.stopBot(id!),
    onSuccess: () => {
      navigate(`/meetings/${id}`);
    },
  });

  const meeting = dbMeeting ? {
    id: dbMeeting.id,
    title: dbMeeting.title || "Untitled Meeting",
    meetingType: (dbMeeting.platform || "meet") as "meet" | "teams" | "zoom" | "webex" | "uploaded",
    status: dbMeeting.status,
  } : {
    id: id || "mock",
    title: "Live Recording Sync",
    meetingType: "meet" as "meet" | "teams" | "zoom" | "webex" | "uploaded",
    status: "recording",
  };

  // Control buttons state (mock toggles)
  const [isMuted, setIsMuted] = useState(false);
  const [isCameraOff, setIsCameraOff] = useState(false);
  const [isSharing, setIsSharing] = useState(false);

  const muteMutation = useMutation({
    mutationFn: (muted: boolean) => meetingsApi.mute(id!, muted),
  });

  const toggleMute = () => {
    const nextMute = !isMuted;
    setIsMuted(nextMute);
    if (id && id !== "mock") {
      muteMutation.mutate(nextMute);
    }
  };

  // Live state
  const [meetingStatus, setMeetingStatus] = useState<string>("joining");
  const [pipelineStep, setPipelineStep] = useState<"transcribing" | "summarising" | "finalising" | "done">("transcribing");
  const [elapsed, setElapsed] = useState(0); 
  const [activeSpeaker, setActiveSpeaker] = useState("");
  const [monologueTimer, setMonologueTimer] = useState(0);

  useEffect(() => {
    if (id === "mock") {
      setMeetingStatus("recording");
    } else if (dbMeeting?.status) {
      setMeetingStatus(dbMeeting.status);
      if (dbMeeting.status === "done" && pipelineStep !== "done") {
        setPipelineStep("done");
        setTimeout(() => navigate(`/meetings/${id}`), 1500);
      }
    }
  }, [dbMeeting, id, navigate, pipelineStep]);

  useWebSocket({
    meetingId: id || "",
    enabled: !!id && id !== "mock",
    onEvent: (event: any) => {
      if (event.type === "transcript_segment" || event.type === "segment") {
        const segmentData = event.segment || event.payload;
        if (!segmentData) return;

        const timeStr = formatElapsed(Math.floor((segmentData.start_ms || 0) / 1000));
        const speaker = segmentData.speaker_name || segmentData.speaker || "Speaker";

        setLiveTranscript((prev) => [
          ...prev,
          {
            speaker: speaker,
            text: segmentData.text || "",
            time: timeStr,
          },
        ]);
        setActiveSpeaker((current) => {
          if (current !== speaker) {
            setMonologueTimer(0);
          }
          return speaker;
        });
        setTalkTimes((prev) => {
          if (!prev[speaker]) {
            return { ...prev, [speaker]: 0 };
          }
          return prev;
        });
      } else if (event.type === "status_change") {
        setMeetingStatus(event.status);
        if (event.status === "done") {
          setPipelineStep("done");
          setTimeout(() => navigate(`/meetings/${id}`), 1500);
        } else if (event.status === "error") {
          navigate(`/meetings/${id}`);
        }
      } else if (event.type === "pipeline_started" as any) {
        setMeetingStatus("processing");
        setPipelineStep("transcribing");
      } else if (event.type === "transcribed" as any) {
        setPipelineStep("summarising");
      } else if (event.type === "summarised" as any) {
        setPipelineStep("finalising");
      } else if (event.type === "done" as any) {
        setMeetingStatus("done");
        setPipelineStep("done");
        setTimeout(() => navigate(`/meetings/${id}`), 1500);
      } else if (event.type === "error" as any) {
        navigate(`/meetings/${id}`);
      }
    },
  });

  const [liveTranscript, setLiveTranscript] = useState<{ speaker: string; text: string; time: string; lowConfidence?: boolean }[]>([]);

  const [aiNotes, setAiNotes] = useState<{ id: string; text: string; isSaved?: boolean }[]>([]);

  const [liveActions, setLiveActions] = useState<{ id: string; text: string; isSaved?: boolean }[]>([]);

  const [talkTimes, setTalkTimes] = useState<Record<string, number>>({});

  // Sentiment real-time updating data
  const [liveSentiment, setLiveSentiment] = useState<{ name: string; value: number }[]>([]);

  const [chatInput, setChatInput] = useState("");
  const [liveChat, setLiveChat] = useState<{ role: "user" | "assistant"; text: string }[]>([]);

  // Simulation dialogue pools
  const dialoguePool = [
    { speaker: "Jay Shah", text: "Should we use Framer Motion for the layout springs, or keep it strictly CSS transitions to optimize render performance?" },
    { speaker: "Mia Wong", text: "Framer Motion gives us spring physics control, which feels much more premium. Let's use it for collapsible sidebars and command overlays.", lowConfidence: true },
    { speaker: "Rahul Patel", text: "Let's align on Framer Motion. But keep the core buttons and list animations as light CSS transitions to keep load times under 800ms." },
    { speaker: "Jay Shah", text: "Okay, I will document that constraint. I can set up the initial wrappers inside the packages folder." },
    { speaker: "Rahul Patel", text: "Great. Let's also add an option to toggle between light and dark modes in the settings footer." },
  ];

  const dialogueIndex = useRef(0);
  const transcriptBottomRef = useRef<HTMLDivElement>(null);

  // Time Tick
  useEffect(() => {
    const timer = setInterval(() => {
      setElapsed((prev) => prev + 1);
      setMonologueTimer((prev) => prev + 1);
      
      // Dynamic talk time increment based on active speaker
      setActiveSpeaker((active) => {
        if (active) {
          setTalkTimes((prev) => ({
            ...prev,
            [active]: (prev[active] || 0) + 1,
          }));
        }
        return active;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    const sentimentTimer = setInterval(() => {
      setLiveSentiment((prev) => {
        const nextTime = (prev.length * 5) + "s";
        const lastVal = prev.length > 0 ? prev[prev.length - 1].value : 75;
        // Float between 70% and 95%
        const delta = Math.floor(Math.random() * 11) - 5; // -5 to +5
        const nextVal = Math.min(95, Math.max(70, lastVal + delta));
        const updated = [...prev, { name: nextTime, value: nextVal }];
        return updated.slice(-8); // Keep last 8 points
      });
    }, 5000);
    return () => clearInterval(sentimentTimer);
  }, []);

  // Scroll to bottom of live transcript
  useEffect(() => {
    transcriptBottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [liveTranscript]);

  const formatElapsed = (sec: number) => {
    const mins = Math.floor(sec / 60);
    const secs = sec % 60;
    return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  };

  const handleEndMeeting = () => {
    if (id && id !== "mock") {
      stopBotMutation.mutate();
    } else {
      navigate(`/meetings/mock`);
    }
  };

  const handleChatSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!chatInput) return;
    const userText = chatInput;
    setLiveChat((prev) => [...prev, { role: "user", text: userText }]);
    setChatInput("");

    setTimeout(() => {
      let reply = "I'm compiling the live context. Currently, the team has confirmed Indigo as the theme accent and agreed to adopt Framer Motion for sidebars while keeping CSS transitions for lists.";
      if (userText.toLowerCase().includes("framer")) {
        reply = "Yes, Framer Motion will be used for layouts (collapsibles) to add premium spring physics, while keeping button transitions light.";
      }
      setLiveChat((prev) => [...prev, { role: "assistant", text: reply }]);
    }, 1000);
  };

  // Saved note visual toggler
  const handleSaveNote = (id: string, isAction: boolean = false) => {
    if (isAction) {
      setLiveActions((prev) =>
        prev.map((act) => (act.id === id ? { ...act, isSaved: true } : act))
      );
    } else {
      setAiNotes((prev) =>
        prev.map((note) => (note.id === id ? { ...note, isSaved: true } : note))
      );
    }
  };

  // Note inline editing
  const handleEditNoteText = (id: string, newText: string, isAction: boolean = false) => {
    if (isAction) {
      setLiveActions((prev) =>
        prev.map((act) => (act.id === id ? { ...act, text: newText } : act))
      );
    } else {
      setAiNotes((prev) =>
        prev.map((note) => (note.id === id ? { ...note, text: newText } : note))
      );
    }
  };

  // Compute stats
  const totalTalk = Object.values(talkTimes).reduce((a, b) => a + b, 0);

  // Dynamic Sentiment Values
  const lastPositivePct = liveSentiment.length > 0 ? liveSentiment[liveSentiment.length - 1].value : 80;
  const neutralPct = Math.round((100 - lastPositivePct) * 0.8);
  const negativePct = Math.max(0, 100 - lastPositivePct - neutralPct);

  // Dynamic Coaching Advice
  let coachingAdvice = "Analyzing sentiment trend...";
  if (lastPositivePct >= 85) {
    coachingAdvice = "AI consensus: Active momentum is very high. Great collaboration!";
  } else if (lastPositivePct >= 75) {
    coachingAdvice = "AI consensus: Positive momentum. Keep pushing key action items.";
  } else if (liveSentiment.length > 0) {
    coachingAdvice = "AI consensus: Meeting is stable. Encourage participants to contribute.";
  }

  // Dynamic Monologue Warning
  const otherSpeakers = Object.keys(talkTimes).filter((name) => name !== activeSpeaker);
  const otherSpeakersList = otherSpeakers.length > 0 ? otherSpeakers.join(" or ") : "other participants";

  // Speaker assigned tints
  const getSpeakerColor = (name: string) => {
    if (name === "Rahul Patel") return styles.colorRahul;
    if (name === "Mia Wong") return styles.colorMia;
    return styles.colorJay;
  };

  // Conditional rendering based on meeting status
  if (meetingStatus === "joining") {
    return (
      <div className={styles.statusContainer}>
        <div className={styles.statusCard}>
          <div className={styles.statusIconWrapper}>
            <div className={styles.pulseRing} />
            <div className={styles.pulseRing} />
            <div className={styles.pulsingCircle}>
              <PlayCircle size={32} />
            </div>
          </div>
          <h2 className={styles.statusTitle}>Zapper Bot is joining the call...</h2>
          <p className={styles.statusText}>
            Our recorder bot is spawning in a secure container, launching a headless browser, and navigating to your meeting link.
          </p>
          <div className={styles.pipelineTimeline}>
            <div className={styles.pipelineStep}>
              <span className={`${styles.stepIcon} ${styles.completed}`}><Check size={12} /></span>
              <span className={`${styles.stepLabel} ${styles.completed}`}>Virtual container initialized</span>
            </div>
            <div className={styles.pipelineStep}>
              <span className={`${styles.stepIcon} ${styles.active}`}><Clock size={12} /></span>
              <span className={`${styles.stepLabel} ${styles.active}`}>Navigating to Google Meet...</span>
            </div>
            <div className={styles.pipelineStep}>
              <span className={`${styles.stepIcon} ${styles.pending}`}>3</span>
              <span className={`${styles.stepLabel} ${styles.pending}`}>Waiting to request admission</span>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (meetingStatus === "lobby") {
    return (
      <div className={styles.statusContainer}>
        <div className={styles.statusCard}>
          <div className={styles.statusIconWrapper}>
            <div className={`${styles.pulseRing} ${styles.lobby}`} />
            <div className={`${styles.pulseRing} ${styles.lobby}`} />
            <div className={`${styles.pulsingCircle} ${styles.lobby}`}>
              <Users size={32} />
            </div>
          </div>
          <h2 className={styles.statusTitle}>Waiting in meeting lobby</h2>
          <p className={styles.statusText}>
            The recorder bot has reached the join screen and is waiting to be admitted by a host.
          </p>
          <div className={styles.instructionBox}>
            <div className={styles.instructionTitle}>
              <AlertCircle size={14} />
              Host Action Required
            </div>
            <p className={styles.instructionDesc}>
              Please check your Google Meet window and accept the admission request for <strong>{import.meta.env.VITE_BOT_DISPLAY_NAME || "Zapper Recorder"}</strong>.
            </p>
          </div>
          <div className={styles.pipelineTimeline}>
            <div className={styles.pipelineStep}>
              <span className={`${styles.stepIcon} ${styles.completed}`}><Check size={12} /></span>
              <span className={`${styles.stepLabel} ${styles.completed}`}>Zapper container initialized</span>
            </div>
            <div className={styles.pipelineStep}>
              <span className={`${styles.stepIcon} ${styles.completed}`}><Check size={12} /></span>
              <span className={`${styles.stepLabel} ${styles.completed}`}>Navigated to Google Meet</span>
            </div>
            <div className={styles.pipelineStep}>
              <span className={`${styles.stepIcon} ${styles.active}`}><Clock size={12} /></span>
              <span className={`${styles.stepLabel} ${styles.active}`}>Waiting to be admitted...</span>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (meetingStatus === "processing" || meetingStatus === "done") {
    return (
      <div className={styles.statusContainer}>
        <div className={styles.statusCard}>
          <div className={styles.statusIconWrapper}>
            <div className={`${styles.pulseRing} ${styles.processing}`} />
            <div className={`${styles.pulseRing} ${styles.processing}`} />
            <div className={`${styles.pulsingCircle} ${styles.processing}`}>
              {meetingStatus === "done" ? <Check size={32} /> : <Brain size={32} />}
            </div>
          </div>
          <h2 className={styles.statusTitle}>
            {meetingStatus === "done" ? "Processing complete!" : "AI post-processing active..."}
          </h2>
          <p className={styles.statusText}>
            {meetingStatus === "done" 
              ? "All transcription and summary insights have been compiled. Redirecting..." 
              : "The call has ended. Zapper is running the AI analysis pipeline to extract notes, action items, and compute speaker analytics."}
          </p>
          
          <div className={styles.pipelineTimeline}>
            <div className={styles.pipelineStep}>
              <span className={`${styles.stepIcon} ${styles.completed}`}><Check size={12} /></span>
              <span className={`${styles.stepLabel} ${styles.completed}`}>Audio file saved</span>
            </div>
            <div className={styles.pipelineStep}>
              <span className={`${styles.stepIcon} ${
                pipelineStep === "transcribing" ? styles.active : styles.completed
              }`}>
                {pipelineStep === "transcribing" ? <Clock size={12} /> : <Check size={12} />}
              </span>
              <span className={`${styles.stepLabel} ${
                pipelineStep === "transcribing" ? styles.active : styles.completed
              }`}>
                Transcribing audio recording
              </span>
            </div>
            <div className={styles.pipelineStep}>
              <span className={`${styles.stepIcon} ${
                pipelineStep === "transcribing" ? styles.pending :
                pipelineStep === "summarising" ? styles.active : styles.completed
              }`}>
                {pipelineStep === "transcribing" ? "3" :
                 pipelineStep === "summarising" ? <Clock size={12} /> : <Check size={12} />}
              </span>
              <span className={`${styles.stepLabel} ${
                pipelineStep === "transcribing" ? styles.pending :
                pipelineStep === "summarising" ? styles.active : styles.completed
              }`}>
                Generating AI summaries & speaker map
              </span>
            </div>
            <div className={styles.pipelineStep}>
              <span className={`${styles.stepIcon} ${
                pipelineStep === "finalising" ? styles.active :
                pipelineStep === "done" ? styles.completed : styles.pending
              }`}>
                {pipelineStep === "done" ? <Check size={12} /> :
                 pipelineStep === "finalising" ? <Clock size={12} /> : "4"}
              </span>
              <span className={`${styles.stepLabel} ${
                pipelineStep === "finalising" ? styles.active :
                pipelineStep === "done" ? styles.completed : styles.pending
              }`}>
                Finalizing action items & notes
              </span>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.container}>
      {/* Top Header Bar Redesign */}
      <div className={styles.topBar}>
        <div className={styles.left}>
          <span className={styles.livePulseDot} />
          <span className={styles.liveLabel}>LIVE RECORDING</span>
          <span className={styles.divider}>|</span>
          <h2 className={styles.title}>{meeting.title}</h2>
          <Badge className="badge-indigo">{meeting.meetingType}</Badge>
          <span className={styles.participantCount}>
            <Users size={12} />
            {id === "mock" ? "3" : (dbMeeting?.participant_count || 0)} online
          </span>
        </div>

        {/* Media Controls Strip */}
        <div className={styles.mediaControls}>
          <button className={clsx(styles.controlBtn, isMuted && styles.controlBtnActive)} onClick={toggleMute}>
            {isMuted ? <MicOff size={16} /> : <Mic size={16} />}
          </button>
          <button className={clsx(styles.controlBtn, isCameraOff && styles.controlBtnActive)} onClick={() => setIsCameraOff(!isCameraOff)}>
            {isCameraOff ? <CameraOff size={16} /> : <Camera size={16} />}
          </button>
          <button className={clsx(styles.controlBtn, isSharing && styles.controlBtnActive)} onClick={() => setIsSharing(!isSharing)}>
            <Monitor size={16} />
          </button>
        </div>

        <div className={styles.right}>
          <div className={styles.timer}>
            <Clock size={16} />
            <span className={styles.monospaceTimer}>{formatElapsed(elapsed)}</span>
          </div>
          <button className={styles.endBtn} onClick={handleEndMeeting}>
            <PhoneOff size={16} />
            End Call
          </button>
        </div>
      </div>

      {/* Monologue Warning Banner */}
      {monologueTimer > 120 && activeSpeaker && (
        <div className={`${styles.monologueAlert} animate-slide-up`}>
          <AlertCircle size={16} />
          <span>
            <strong>Monologue Alert:</strong> {activeSpeaker} has been speaking for {Math.floor(monologueTimer / 60)}m {monologueTimer % 60}s. Consider prompting {otherSpeakersList} for their input to balance participation.
          </span>
        </div>
      )}

      {/* 4-Panel Grid Layout */}
      <div className={styles.grid}>
        
        {/* Panel 1: Live Transcript */}
        <Card className={styles.columnCard}>
          <div className={styles.columnHeader}>
            <MessageSquare size={16} />
            <h3>Live Transcript</h3>
          </div>
          <div className={styles.transcriptList}>
            {liveTranscript.map((line, idx) => (
              <div key={idx} className={styles.transcriptLine}>
                <div className={styles.speakerRow}>
                  <Avatar name={line.speaker} size="xs" />
                  <span className={clsx(styles.speakerName, getSpeakerColor(line.speaker))}>
                    {line.speaker}
                  </span>
                  <span className={styles.lineTime}>{line.time}</span>
                </div>
                <p className={styles.lineText}>
                  {line.lowConfidence ? (
                    <>
                      Framer Motion gives us spring physics control, which feels much more{" "}
                      <span className={styles.lowConfidenceWord} title="Whisper confidence: 64%">
                        premium
                      </span>
                      . Let's use it for collapsible sidebars.
                    </>
                  ) : (
                    line.text
                  )}
                </p>
              </div>
            ))}
            {/* Dynamic typing indicator on the last row if activeSpeaker is speaking */}
            {activeSpeaker && (
              <div className={styles.typingIndicatorRow}>
                <span className={styles.typingSpeaker}>{activeSpeaker} is speaking</span>
                <div className={styles.typingBubbles}>
                  <span className={styles.bubble} />
                  <span className={styles.bubble} />
                  <span className={styles.bubble} />
                </div>
              </div>
            )}
            <div ref={transcriptBottomRef} />
          </div>
        </Card>

        {/* Panel 2: AI Realtime Notes */}
        <Card className={styles.columnCard}>
          <div className={styles.columnHeader}>
            <Brain size={16} className={styles.notesIcon} />
            <h3>AI Copilot Notes</h3>
          </div>
          <div className={styles.notesList}>
            <div className={styles.notesSection}>
              <h4>Decisions Detected</h4>
              {aiNotes.map((note) => (
                <div key={note.id} className={clsx(styles.noteRow, note.isSaved && styles.savedRow)}>
                  <div className={styles.noteMainRow}>
                    <span className={styles.bulletCheck}>
                      {note.isSaved ? <Check size={10} /> : <span className={styles.bulletCheckInner} />}
                    </span>
                    <input
                      type="text"
                      className={styles.noteInput}
                      value={note.text}
                      onChange={(e) => handleEditNoteText(note.id, e.target.value)}
                    />
                  </div>
                  <button className={styles.saveNoteBtn} onClick={() => handleSaveNote(note.id)} disabled={note.isSaved}>
                    {note.isSaved ? "Saved" : <Save size={12} />}
                  </button>
                </div>
              ))}
            </div>

            <div className={styles.notesSection}>
              <h4>Action Items Generated</h4>
              {liveActions.map((act) => (
                <div key={act.id} className={clsx(styles.noteRow, act.isSaved && styles.savedRow)}>
                  <div className={styles.noteMainRow}>
                    <span className={styles.bulletAction} />
                    <input
                      type="text"
                      className={styles.noteInput}
                      value={act.text}
                      onChange={(e) => handleEditNoteText(act.id, e.target.value, true)}
                    />
                  </div>
                  <button className={styles.saveNoteBtn} onClick={() => handleSaveNote(act.id, true)} disabled={act.isSaved}>
                    {act.isSaved ? "Saved" : <Save size={12} />}
                  </button>
                </div>
              ))}
            </div>
          </div>
        </Card>

        {/* Panel 3: Live Sentiment Tracker (New 4th Panel) */}
        <Card className={styles.columnCard}>
          <div className={styles.columnHeader}>
            <Activity size={16} className={styles.sentimentIcon} />
            <h3>Live Sentiment Tracker</h3>
          </div>
          <div className={styles.sentimentContent}>
            <div className={styles.sentimentStats}>
              <div className={styles.sentimentStat}>
                <span className={styles.sentimentValText} style={{ color: "var(--emerald)" }}>{lastPositivePct}%</span>
                <span className={styles.sentimentStatLabel}>Positive</span>
              </div>
              <div className={styles.sentimentStat}>
                <span className={styles.sentimentValText} style={{ color: "var(--text-subtle)" }}>{neutralPct}%</span>
                <span className={styles.sentimentStatLabel}>Neutral</span>
              </div>
              <div className={styles.sentimentStat}>
                <span className={styles.sentimentValText} style={{ color: "var(--red)" }}>{negativePct}%</span>
                <span className={styles.sentimentStatLabel}>Negative</span>
              </div>
            </div>
            
            <div className={styles.sentimentChartContainer}>
              <AreaChart
                data={liveSentiment}
                color="var(--emerald)"
                height={140}
              />
            </div>

            <div className={styles.coachingAlert}>
              <Sparkles size={14} className={styles.alertIcon} />
              <span>{coachingAdvice}</span>
            </div>
          </div>
        </Card>

        {/* Panel 4: Talk Time & Copilot chat */}
        <Card className={styles.columnCard}>
          <div className={styles.columnHeader}>
            <Users size={16} />
            <h3>Speakers & Copilot</h3>
          </div>
          <div className={styles.statsWrapper}>
            <div className={styles.speakerBars}>
              {Object.entries(talkTimes).map(([name, time]) => {
                const pct = Math.round((time / totalTalk) * 100);
                return (
                  <div key={name} className={styles.speakerBarRow}>
                    <div className={styles.speakerBarInfo}>
                      <span className={getSpeakerColor(name)} style={{ fontWeight: 600 }}>{name}</span>
                      <span>{pct}%</span>
                    </div>
                    <div className={styles.barContainer}>
                      <div className={clsx(styles.barFill, getSpeakerColor(name))} style={{ width: `${pct}%`, transition: "width 0.5s ease" }} />
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Active Participants List */}
            {dbMeeting?.participant_names && dbMeeting.participant_names.length > 0 && (
              <div className={styles.participantsSection}>
                <h4>Active on Call</h4>
                <div className={styles.participantsList}>
                  {dbMeeting.participant_names.map((name) => (
                    <div key={name} className={styles.participantRow}>
                      <Avatar name={name} size="xs" />
                      <span className={styles.participantName}>{name}</span>
                      {activeSpeaker === name && <span className={styles.speakingBadge}>speaking</span>}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* AI Assistant Chat in Sidebar */}
            <div className={styles.liveChatWidget}>
              <h4>Ask Zapper Copilot</h4>
              <div className={styles.chatHistory}>
                {liveChat.length === 0 ? (
                  <div className={styles.emptyChatText}>
                    Ask the Copilot questions about live notes, agreements, or transcript history.
                  </div>
                ) : (
                  liveChat.map((msg, idx) => (
                    <div key={idx} className={clsx(styles.chatMsg, msg.role === "user" ? styles.userMsg : styles.assistantMsg)}>
                      <p>{msg.text}</p>
                    </div>
                  ))
                )}
              </div>
              <form onSubmit={handleChatSubmit} className={styles.chatForm}>
                <input
                  type="text"
                  placeholder="Ask live assistant..."
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  className={styles.chatInput}
                />
                <button type="submit" className={styles.chatSendBtn}>
                  <Send size={12} />
                </button>
              </form>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
};

export default LiveMeeting;
