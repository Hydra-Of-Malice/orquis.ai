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
  const [elapsed, setElapsed] = useState(2061); // Start at 34m 21s
  const [activeSpeaker, setActiveSpeaker] = useState("Rahul Patel");
  const [monologueTimer, setMonologueTimer] = useState(195); // 3m 15s speak monologue

  useWebSocket({
    meetingId: id || "",
    enabled: !!id && id !== "mock",
    onEvent: (event: LiveEvent) => {
      if (event.type === "transcript_segment") {
        const timeStr = formatElapsed(Math.floor(event.segment.start_ms / 1000));
        setLiveTranscript((prev) => [
          ...prev,
          {
            speaker: event.segment.speaker_name,
            text: event.segment.text,
            time: timeStr,
          },
        ]);
        setActiveSpeaker((current) => {
          if (current !== event.segment.speaker_name) {
            setMonologueTimer(0);
          }
          return event.segment.speaker_name;
        });
      } else if (event.type === "status_change") {
        if (event.status === "done" || event.status === "error") {
          navigate(`/meetings/${id}`);
        }
      }
    },
  });

  const [liveTranscript, setLiveTranscript] = useState<{ speaker: string; text: string; time: string; lowConfidence?: boolean }[]>([
    { speaker: "Rahul Patel", text: "So, the first milestone is styling tokens. Let's make sure the dark background matches Notion dark, and our accent is a vibrant indigo.", time: "34:02" },
    { speaker: "Mia Wong", text: "Agreed. I think Geist is the best secondary font for readability in data tables. It looks clean and modern.", time: "34:15" },
  ]);

  const [aiNotes, setAiNotes] = useState<{ id: string; text: string; isSaved?: boolean }[]>([
    { id: "note_1", text: "Confirmed Indigo (#6366F1) as primary theme accent color." },
    { id: "note_2", text: "Decided on Geist Mono/Sans as secondary typography font family." },
  ]);

  const [liveActions, setLiveActions] = useState<{ id: string; text: string; isSaved?: boolean }[]>([
    { id: "act_1", text: "Export design styling tokens in CSS variables format." },
    { id: "act_2", text: "Create fallback SVG icons for all Zoom/Meet/Teams badges." },
  ]);

  const [talkTimes, setTalkTimes] = useState<Record<string, number>>({
    "Rahul Patel": 1133,
    "Mia Wong": 618,
    "Jay Shah": 310,
  });

  // Sentiment real-time updating data
  const [liveSentiment, setLiveSentiment] = useState<{ name: string; value: number }[]>([
    { name: "0s", value: 75 },
    { name: "5s", value: 78 },
    { name: "10s", value: 82 },
    { name: "15s", value: 80 },
    { name: "20s", value: 85 },
  ]);

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
    if (id && id !== "mock") return;
    const timer = setInterval(() => {
      setElapsed((prev) => prev + 1);
      setMonologueTimer((prev) => prev + 1);
      
      // Random talk time increment
      const speakers = Object.keys(talkTimes);
      const active = activeSpeaker;
      setTalkTimes((prev) => ({
        ...prev,
        [active]: prev[active] + 1,
      }));
    }, 1000);
    return () => clearInterval(timer);
  }, [talkTimes, activeSpeaker, id]);

  // Dialogue Injector Simulation
  useEffect(() => {
    if (id && id !== "mock") return;
    const injector = setInterval(() => {
      if (dialogueIndex.current < dialoguePool.length) {
        const nextLine = dialoguePool[dialogueIndex.current];
        const minutes = Math.floor((elapsed) / 60);
        const seconds = (elapsed) % 60;
        const timeStr = `${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`;

        setLiveTranscript((prev) => [
          ...prev,
          { speaker: nextLine.speaker, text: nextLine.text, time: timeStr, lowConfidence: nextLine.lowConfidence },
        ]);

        // Change active speaker & reset monologue timer on speaker switch
        setActiveSpeaker((current) => {
          if (current !== nextLine.speaker) {
            setMonologueTimer(0);
          }
          return nextLine.speaker;
        });

        // Auto trigger notes or actions for demo feedback
        if (nextLine.text.includes("Framer Motion")) {
          setAiNotes((prev) => [...prev, { id: `note_${Date.now()}`, text: "Adopted Framer Motion for premium spring layouts." }]);
        }
        if (nextLine.text.includes("light and dark")) {
          setLiveActions((prev) => [...prev, { id: `act_${Date.now()}`, text: "Implement light/dark mode switch in layout footers." }]);
        }

        dialogueIndex.current += 1;
      }
    }, 5500);

    return () => clearInterval(injector);
  }, [elapsed, id]);

  // Real-time Sentiment Updater Tick
  useEffect(() => {
    if (id && id !== "mock") return;
    const sentimentTimer = setInterval(() => {
      setLiveSentiment((prev) => {
        const nextTime = (prev.length * 5) + "s";
        const lastVal = prev[prev.length - 1]?.value || 75;
        // Float between 70% and 95%
        const delta = Math.floor(Math.random() * 11) - 5; // -5 to +5
        const nextVal = Math.min(95, Math.max(70, lastVal + delta));
        const updated = [...prev, { name: nextTime, value: nextVal }];
        return updated.slice(-8); // Keep last 8 points
      });
    }, 5000);
    return () => clearInterval(sentimentTimer);
  }, [id]);

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

  // Speaker assigned tints
  const getSpeakerColor = (name: string) => {
    if (name === "Rahul Patel") return styles.colorRahul;
    if (name === "Mia Wong") return styles.colorMia;
    return styles.colorJay;
  };

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
            3 online
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
      {monologueTimer > 180 && activeSpeaker === "Rahul Patel" && (
        <div className={`${styles.monologueAlert} animate-slide-up`}>
          <AlertCircle size={16} />
          <span>
            <strong>Monologue Alert:</strong> Rahul Patel has been speaking for {Math.floor(monologueTimer / 60)}m {monologueTimer % 60}s. Consider prompting Mia Wong or Jay Shah for their input to balance participation.
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
            {/* Dynamic typing indicator on the last row if simulator is going */}
            <div className={styles.typingIndicatorRow}>
              <span className={styles.typingSpeaker}>{activeSpeaker} is speaking</span>
              <div className={styles.typingBubbles}>
                <span className={styles.bubble} />
                <span className={styles.bubble} />
                <span className={styles.bubble} />
              </div>
            </div>
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
                <span className={styles.sentimentValText} style={{ color: "var(--emerald)" }}>82%</span>
                <span className={styles.sentimentStatLabel}>Positive</span>
              </div>
              <div className={styles.sentimentStat}>
                <span className={styles.sentimentValText} style={{ color: "var(--text-subtle)" }}>15%</span>
                <span className={styles.sentimentStatLabel}>Neutral</span>
              </div>
              <div className={styles.sentimentStat}>
                <span className={styles.sentimentValText} style={{ color: "var(--red)" }}>3%</span>
                <span className={styles.sentimentStatLabel}>Negative</span>
              </div>
            </div>
            
            <div className={styles.sentimentChartContainer}>
              <AreaChart
                data={liveSentiment}
                color="var(--emerald)"
              />
            </div>

            <div className={styles.coachingAlert}>
              <Sparkles size={14} className={styles.alertIcon} />
              <span>AI consensus: Active momentum is high. Push key action items now to lock in decisions.</span>
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
