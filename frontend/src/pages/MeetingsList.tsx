import React, { useState, useEffect } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { meetingsApi } from "../services/meetings";
import { PageHeader } from "../components/layout/PageHeader";
import { Card } from "../components/ui/Card";
import { Input } from "../components/ui/Input";
import { Button } from "../components/ui/Button";
import { Badge } from "../components/ui/Badge";
import { Avatar } from "../components/ui/Avatar";
import { EmptyState } from "../components/ui/EmptyState";
import { JoinMeetingModal } from "../components/modals/JoinMeetingModal";
import {
  Search,
  Film,
  Calendar,
  Eye,
  Download,
  Share2,
  MoreVertical,
  Play,
  Grid,
  List,
  Clock,
  ChevronRight,
  TrendingUp,
  AlertCircle,
  HelpCircle,
  X,
  FileText,
  Loader2
} from "lucide-react";
import styles from "./MeetingsList.module.css";
import clsx from "clsx";

interface MeetingsListProps {
  onOpenCommandPalette?: () => void;
  defaultFilter?: "all" | "live" | "upcoming" | "recordings" | "uploaded";
}

export const MeetingsList: React.FC<MeetingsListProps> = ({
  onOpenCommandPalette,
  defaultFilter,
}) => {
  const navigate = useNavigate();
  const location = useLocation();

  const isLive = (status: string) => {
    return status === "joining" || status === "lobby" || status === "recording" || status === "live";
  };

  const { data: rawMeetings = [], isLoading } = useQuery({
    queryKey: ["meetings"],
    queryFn: () => meetingsApi.list({ limit: 100 }),
    refetchInterval: 5000,
    retry: 1,
  });

  const meetings = rawMeetings.map((m: any) => ({
    id: m.id,
    title: m.title || "Untitled Meeting",
    meetingType: m.platform || "meet",
    startedAt: m.started_at || new Date().toISOString(),
    endedAt: m.ended_at,
    durationSeconds: m.duration_seconds || 0,
    status: m.status === "done" ? "completed" : m.status,
    healthScore: m.health_score || undefined,
    engagementScore: m.engagement_score || undefined,
    sentiment: m.sentiment,
    participantNames: m.participant_names || [],
    participantCount: m.participant_count || 0,
    summaryMd: m.summary_md || "",
  }));

  // Set filter based on prop or route matching
  const getInitialFilter = () => {
    if (defaultFilter) return defaultFilter;
    if (location.pathname.includes("/live")) return "live";
    if (location.pathname.includes("/upcoming")) return "upcoming";
    if (location.pathname.includes("/recordings")) return "recordings";
    return "all";
  };

  const [filter, setFilter] = useState<string>(getInitialFilter);
  const [search, setSearch] = useState("");
  const [platformFilter, setPlatformFilter] = useState("all");
  const [durationFilter, setDurationFilter] = useState("all");
  const [sortFilter, setSortFilter] = useState("newest");
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid");
  const [isJoinOpen, setIsJoinOpen] = useState(false);

  useEffect(() => {
    setFilter(getInitialFilter());
  }, [defaultFilter, location.pathname]);

  // Filtering Logic
  const filteredMeetings = meetings.filter((m) => {
    // Search match
    const searchMatch = m.title.toLowerCase().includes(search.toLowerCase());
    
    // Primary tabs filter
    let statusMatch = true;
    if (filter === "live") statusMatch = isLive(m.status);
    else if (filter === "upcoming") statusMatch = m.status === "scheduled";
    else if (filter === "recordings") statusMatch = m.status === "completed" || m.status === "processing";
    else if (filter === "uploaded") statusMatch = m.meetingType === "uploaded";

    // Secondary platform filter
    let platformMatch = true;
    if (platformFilter !== "all") {
      platformMatch = m.meetingType === platformFilter;
    }

    // Secondary duration filter
    let durationMatch = true;
    if (durationFilter !== "all") {
      const mins = m.durationSeconds / 60;
      if (durationFilter === "short") durationMatch = mins < 30;
      else if (durationFilter === "medium") durationMatch = mins >= 30 && mins <= 60;
      else if (durationFilter === "long") durationMatch = mins > 60;
    }

    return searchMatch && statusMatch && platformMatch && durationMatch;
  });

  // Sorting Logic
  const sortedMeetings = [...filteredMeetings].sort((a, b) => {
    if (sortFilter === "newest") {
      return new Date(b.startedAt).getTime() - new Date(a.startedAt).getTime();
    }
    if (sortFilter === "oldest") {
      return new Date(a.startedAt).getTime() - new Date(b.startedAt).getTime();
    }
    if (sortFilter === "health-high") {
      return (b.healthScore || 0) - (a.healthScore || 0);
    }
    if (sortFilter === "health-low") {
      return (a.healthScore || 999) - (b.healthScore || 999);
    }
    return 0;
  });

  // Smart duration format: Xs / M:SS min / Xh Ym
  const formatDuration = (seconds: number) => {
    if (!seconds || seconds <= 0) return "0s";
    if (seconds < 60) return `${seconds}s`;
    const totalMins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    if (totalMins < 60) {
      return secs > 0 ? `${totalMins}:${String(secs).padStart(2, "0")} min` : `${totalMins} min`;
    }
    const hrs = Math.floor(totalMins / 60);
    const remainingMins = totalMins % 60;
    return remainingMins > 0 ? `${hrs}h ${remainingMins}m` : `${hrs}h`;
  };

  const getPlatformClass = (type: string) => {
    if (type === "zoom") return styles.zoomBadge;
    if (type === "teams") return styles.teamsBadge;
    if (type === "meet") return styles.meetBadge;
    return styles.uploadedBadge;
  };

  const getHealthColor = (score: number) => {
    if (score >= 80) return "var(--emerald)";
    if (score >= 60) return "var(--amber)";
    return "var(--red)";
  };

  // Grouping sorted meetings for better UI breakdown
  const liveSection = sortedMeetings.filter(m => isLive(m.status));
  const processingSection = sortedMeetings.filter(m => m.status === "processing");
  const completedSection = sortedMeetings.filter(m => !isLive(m.status) && m.status !== "processing");

  const clearFilters = () => {
    setSearch("");
    setPlatformFilter("all");
    setDurationFilter("all");
    setSortFilter("newest");
  };

  const hasActiveFilters = search !== "" || platformFilter !== "all" || durationFilter !== "all";

  return (
    <div className={styles.container}>
      <PageHeader
        breadcrumbs={["Meetings", filter.charAt(0).toUpperCase() + filter.slice(1)]}
        onOpenCommandPalette={onOpenCommandPalette}
      />

      <div className={styles.content}>
        
        {/* Advanced Filter Bar */}
        <div className={`${styles.filterContainer} glass-card`}>
          <div className={styles.tabsRow}>
            <div className={styles.tabs}>
              {(["all", "live", "upcoming", "recordings", "uploaded"] as const).map((tab) => (
                <button
                  key={tab}
                  className={clsx(styles.tabBtn, filter === tab && styles.tabActive)}
                  onClick={() => {
                    navigate(`/meetings/${tab}`);
                  }}
                >
                  {tab.charAt(0).toUpperCase() + tab.slice(1)}
                </button>
              ))}
            </div>
            
            <div className={styles.viewToggle}>
              <button
                className={clsx(styles.toggleBtn, viewMode === "grid" && styles.toggleActive)}
                onClick={() => setViewMode("grid")}
                title="Grid View"
              >
                <Grid size={16} />
              </button>
              <button
                className={clsx(styles.toggleBtn, viewMode === "list" && styles.toggleActive)}
                onClick={() => setViewMode("list")}
                title="Table List View"
              >
                <List size={16} />
              </button>
            </div>
          </div>

          <div className={styles.selectorsRow}>
            <div className={styles.searchInputWrapper}>
              <Search size={16} className={styles.searchIcon} />
              <input
                type="text"
                placeholder="Search meeting titles, highlights..."
                className={styles.searchField}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
              {search && (
                <button className={styles.clearSearch} onClick={() => setSearch("")}>
                  <X size={14} />
                </button>
              )}
            </div>

            <div className={styles.selects}>
              <select
                className={styles.filterSelect}
                value={platformFilter}
                onChange={(e) => setPlatformFilter(e.target.value)}
              >
                <option value="all">All Platforms</option>
                <option value="zoom">Zoom</option>
                <option value="meet">Google Meet</option>
                <option value="teams">MS Teams</option>
                <option value="uploaded">Uploaded Files</option>
              </select>

              <select
                className={styles.filterSelect}
                value={durationFilter}
                onChange={(e) => setDurationFilter(e.target.value)}
              >
                <option value="all">All Durations</option>
                <option value="short">&lt; 30 mins</option>
                <option value="medium">30 - 60 mins</option>
                <option value="long">&gt; 60 mins</option>
              </select>

              <select
                className={styles.filterSelect}
                value={sortFilter}
                onChange={(e) => setSortFilter(e.target.value)}
              >
                <option value="newest">Newest First</option>
                <option value="oldest">Oldest First</option>
                <option value="health-high">Health (High to Low)</option>
                <option value="health-low">Health (Low to High)</option>
              </select>
            </div>
          </div>
        </div>

        {/* Grouped Content Listings */}
        {isLoading ? (
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "4rem", gap: "1rem", color: "var(--text-muted)" }}>
            <Loader2 size={32} className="spin" />
            <p>Loading sessions...</p>
          </div>
        ) : sortedMeetings.length > 0 ? (
          <div className={styles.listingsScroll}>
            {/* 🔴 LIVE NOW SECTION */}
            {liveSection.length > 0 && (
              <div className={styles.groupSection}>
                <div className={styles.sectionHeader}>
                  <span className={styles.pulseDotRed} />
                  <h2>Live Meetings</h2>
                  <Badge className="badge-red">{liveSection.length} active</Badge>
                </div>
                <div className={viewMode === "grid" ? styles.grid : styles.listView}>
                  {liveSection.map((m) => renderMeetingItem(m))}
                </div>
              </div>
            )}

            {/* ⏳ PROCESSING SECTION */}
            {processingSection.length > 0 && (
              <div className={styles.groupSection}>
                <div className={styles.sectionHeader}>
                  <span className={styles.pulseDotAmber} />
                  <h2>Analyzing & Processing</h2>
                  <Badge className="badge-amber">{processingSection.length} in progress</Badge>
                </div>
                <div className={viewMode === "grid" ? styles.grid : styles.listView}>
                  {processingSection.map((m) => renderMeetingItem(m))}
                </div>
              </div>
            )}

            {/* ✅ COMPLETED / COMPLETED RECORDINGS */}
            {completedSection.length > 0 && (
              <div className={styles.groupSection}>
                <div className={styles.sectionHeader}>
                  <h2>Completed Sessions</h2>
                  <Badge className="badge-gray">{completedSection.length} total</Badge>
                </div>
                <div className={viewMode === "grid" ? styles.grid : styles.listView}>
                  {completedSection.map((m) => renderMeetingItem(m))}
                </div>
              </div>
            )}
          </div>
        ) : (
          <EmptyState
            icon={Film}
            title={hasActiveFilters ? "No matches found" : "No meetings yet"}
            description={
              hasActiveFilters
                ? "No meetings correspond to your active query or selected dropdown filters. Try broadening your terms."
                : "You don't have any recordings in this category. Join a call to start tracking in real-time."
            }
            actionText={hasActiveFilters ? "Reset Filters" : "Call Zapper Bot"}
            onAction={hasActiveFilters ? clearFilters : () => setIsJoinOpen(true)}
          />
        )}
      </div>
      
      <JoinMeetingModal isOpen={isJoinOpen} onClose={() => setIsJoinOpen(false)} />
    </div>
  );

  // Render sub-components dynamically for layout flexibility
  function renderMeetingItem(m: any) {
    const healthColor = getHealthColor(m.healthScore || 0);
    const displayTime = new Date(m.startedAt).toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
    }) + " • " + new Date(m.startedAt).toLocaleTimeString(undefined, {
      hour: "2-digit",
      minute: "2-digit",
    });

    // Real excerpt: use summary_md first two sentences, else status message
    const rawSummary = (m as any).summaryMd || "";
    const sentenceMatch = rawSummary.match(/[^.!?]*[.!?]/g);
    const realExcerpt = sentenceMatch && sentenceMatch.length > 0
      ? sentenceMatch.slice(0, 2).join(" ").trim()
      : "";

    const statusExcerpt = m.status === "completed"
      ? "Meeting complete. Click to view AI summary, transcript, and action items."
      : m.status === "processing"
      ? "AI is transcribing audio, matching speakers, and generating insights…"
      : "Call active — live Whisper transcription streaming.";

    const excerpt = realExcerpt || statusExcerpt;

    // Participant avatars: max 3 shown, rest as +N
    const names: string[] = m.participantNames && m.participantNames.length > 0
      ? m.participantNames
      : [];
    const visibleNames = names.slice(0, 3);
    const overflowCount = names.length - visibleNames.length;

    if (viewMode === "list") {
      // TABLE LIST ROW LAYOUT
      return (
        <div
          key={m.id}
          className={clsx(styles.listRow, m.status === "processing" && styles.processingRow)}
          onClick={() => navigate(isLive(m.status) ? `/live/${m.id}` : `/meetings/${m.id}`)}
        >
          <div className={styles.platformBadgeCell}>
            <Badge className={getPlatformClass(m.meetingType)}>
              {m.meetingType}
            </Badge>
          </div>
          
          <div className={styles.rowMainInfo}>
            <span className={styles.rowTitle}>{m.title}</span>
            <span className={styles.rowExcerpt}>{excerpt}</span>
          </div>

          <div className={styles.rowTimeCell}>
            <Clock size={12} />
            <span>{displayTime}</span>
          </div>

          <div className={styles.rowDurationCell}>
            <span>{formatDuration(m.durationSeconds)}</span>
          </div>

          <div className={styles.rowAvatars}>
            <div className={styles.avatarsList}>
              {visibleNames.map((name) => (
                <Avatar key={name} name={name} size="xs" />
              ))}
              {overflowCount > 0 && (
                <span className={styles.avatarOverflow}>+{overflowCount}</span>
              )}
            </div>
          </div>

          {m.healthScore ? (
            <div className={styles.rowHealthBadge}>
              <span className={styles.healthDot} style={{ backgroundColor: healthColor }} />
              <span className={styles.healthScoreText}>{m.healthScore} Health</span>
            </div>
          ) : (
            <div className={styles.rowHealthBadge}>
              <span className={styles.healthDot} style={{ backgroundColor: "var(--text-muted)" }} />
              <span className={styles.healthScoreText} style={{ color: "var(--text-muted)" }}>--</span>
            </div>
          )}

          <div className={styles.rowCta}>
            <Button variant="ghost" size="sm">
              <ChevronRight size={16} />
            </Button>
          </div>
        </div>
      );
    }

    // MODERN CARD GRID LAYOUT
    return (
      <Card
        key={m.id}
        className={clsx(styles.meetingCard, m.status === "processing" && styles.processingCard)}
        onClick={() => navigate(isLive(m.status) ? `/live/${m.id}` : `/meetings/${m.id}`)}
      >
        {/* Color Strip Header */}
        <div className={clsx(styles.platformStrip, styles[`strip-${m.meetingType}`])} />

        <div className={styles.cardPadding}>
          <div className={styles.cardHeader}>
            <Badge className={getPlatformClass(m.meetingType)}>
              {m.meetingType}
            </Badge>
            
            {isLive(m.status) ? (
              <span className={styles.liveIndicator}>
                <span className={styles.liveDot} />
                {m.status === "joining" ? "BOT JOINING" : m.status === "lobby" ? "IN LOBBY" : "LIVE NOW"}
              </span>
            ) : m.status === "processing" ? (
              <span className={styles.processingIndicator}>
                <span className={styles.pulseBar} />
                PROCESSING
              </span>
            ) : (
              <span className={styles.dateLabel}>
                {formatDuration(m.durationSeconds)}
              </span>
            )}
          </div>

          <div className={styles.cardBody}>
            <h3 className={styles.meetingTitle}>{m.title}</h3>
            <span className={styles.cardDisplayTime}>{displayTime}</span>
            <p className={styles.cardExcerpt}>{excerpt}</p>
          </div>

          <div className={styles.cardFooter}>
            <div className={styles.avatarsList}>
              {visibleNames.map((name) => (
                <Avatar key={name} name={name} size="xs" />
              ))}
              {overflowCount > 0 && (
                <span className={styles.avatarOverflow}>+{overflowCount}</span>
              )}
              {visibleNames.length === 0 && (
                <span className={styles.noParticipants}>No participants</span>
              )}
            </div>

            {m.healthScore && (
              <div className={styles.healthContainer} title={`Health Score: ${m.healthScore}%`}>
                <svg className={styles.svgRing} width="32" height="32">
                  <circle className={styles.circleBg} cx="16" cy="16" r="12" />
                  <circle
                    className={styles.circleFg}
                    cx="16"
                    cy="16"
                    r="12"
                    stroke={healthColor}
                    style={{ strokeDashoffset: 75.4 - (75.4 * m.healthScore) / 100 }}
                  />
                </svg>
                <span className={styles.healthVal}>{m.healthScore}</span>
              </div>
            )}
          </div>
        </div>
      </Card>
    );
  }
};

export default MeetingsList;
