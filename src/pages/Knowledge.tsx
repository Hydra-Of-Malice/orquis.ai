import React, { useState, useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../services/api";
import { meetingsApi } from "../services/meetings";
import { PageHeader } from "../components/layout/PageHeader";
import { Card } from "../components/ui/Card";
import { Badge } from "../components/ui/Badge";
import { Avatar } from "../components/ui/Avatar";
import { Button } from "../components/ui/Button";
import {
  FolderOpen, Lightbulb, Users, Tag, Search, Sparkles, ArrowRight, Loader2, Clock
} from "lucide-react";
import styles from "./Knowledge.module.css";
import clsx from "clsx";

export const Knowledge: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();

  const getInitialTab = () => {
    if (location.pathname.includes("/topics")) return "topics";
    if (location.pathname.includes("/people")) return "people";
    return "projects";
  };

  const [activeSubTab, setActiveSubTab] = useState<"projects" | "topics" | "people">(getInitialTab);
  const [searchTerm, setSearchTerm] = useState("");

  useEffect(() => {
    setActiveSubTab(getInitialTab());
  }, [location.pathname]);

  // ── Real API queries ────────────────────────────────────────────────────────
  const { data: meetings = [], isLoading: meetingsLoading } = useQuery({
    queryKey: ["meetings"],
    queryFn: () => meetingsApi.list({ limit: 100 }),
  });

  const { data: topics = [], isLoading: topicsLoading } = useQuery({
    queryKey: ["knowledge-topics"],
    queryFn: () => api.get("/knowledge/topics").then(r => r.data),
    enabled: activeSubTab === "topics",
  });

  const { data: decisions = [], isLoading: decisionsLoading } = useQuery({
    queryKey: ["knowledge-decisions"],
    queryFn: () => api.get("/knowledge/decisions").then(r => r.data),
    enabled: activeSubTab === "topics",
  });

  const { data: people = [], isLoading: peopleLoading } = useQuery({
    queryKey: ["knowledge-people"],
    queryFn: () => api.get("/knowledge/people").then(r => r.data),
    enabled: activeSubTab === "people",
  });

  // ── Filtering ──────────────────────────────────────────────────────────────
  // Projects = deduplicated from real meetings (group by title prefix or org)
  const completedMeetings = (meetings as any[]).filter(m => m.status === "done" || m.status === "completed");
  const recentProjects = completedMeetings.slice(0, 9); // treat last 9 meetings as "projects"

  const filteredTopics = (topics as any[]).filter(t =>
    t.name.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const filteredPeople = (people as any[]).filter(p =>
    p.name.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const filteredDecisions = (decisions as any[]).filter(d =>
    d.decision?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    d.meeting_title?.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const isLoading = activeSubTab === "topics" ? (topicsLoading || decisionsLoading) :
    activeSubTab === "people" ? peopleLoading : meetingsLoading;

  return (
    <div className={styles.container}>
      <PageHeader
        breadcrumbs={["Knowledge Hub", activeSubTab.charAt(0).toUpperCase() + activeSubTab.slice(1)]}
      />

      {/* Sub navigation */}
      <div className={styles.subTabBar}>
        <button className={clsx(styles.subTabBtn, activeSubTab === "projects" && styles.subTabActive)}
          onClick={() => { setActiveSubTab("projects"); setSearchTerm(""); }}>
          Meetings Catalog
        </button>
        <button className={clsx(styles.subTabBtn, activeSubTab === "topics" && styles.subTabActive)}
          onClick={() => { setActiveSubTab("topics"); setSearchTerm(""); }}>
          Topics Explorer
        </button>
        <button className={clsx(styles.subTabBtn, activeSubTab === "people" && styles.subTabActive)}
          onClick={() => { setActiveSubTab("people"); setSearchTerm(""); }}>
          People Profiles
        </button>
      </div>

      <div className={styles.content}>
        {/* Search Bar */}
        <div className={`${styles.searchRow} glass-card`}>
          <Search size={16} className={styles.searchIcon} />
          <input type="text" placeholder={`Filter ${activeSubTab}...`}
            className={styles.searchInput} value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)} />
        </div>

        {isLoading ? (
          <div className={styles.loadingState}>
            <Loader2 size={22} className={styles.spinner} />
            <span>Loading {activeSubTab}...</span>
          </div>
        ) : (
          <>
            {/* ═══ MEETINGS / PROJECTS ═══ */}
            {activeSubTab === "projects" && (
              <div className={styles.projects}>
                {recentProjects.length === 0 ? (
                  <div className={styles.emptyState}>
                    <FolderOpen size={36} />
                    <p>No meetings yet. Start recording a meeting to build your knowledge base.</p>
                  </div>
                ) : (
                  <div className={styles.grid}>
                    {recentProjects.map((meeting: any) => (
                      <Card key={meeting.id} className={styles.projCard} interactive
                        onClick={() => navigate(`/meetings/${meeting.id}`)}>
                        <div className={styles.projHeader}>
                          <div className={styles.iconCircle} style={{ backgroundColor: "#6366f115", color: "#6366f1" }}>
                            <FolderOpen size={20} />
                          </div>
                          <Badge className="badge-gray">
                            {meeting.status === "done" || meeting.status === "completed" ? "Completed" : meeting.status}
                          </Badge>
                        </div>
                        <h3 className={styles.projName}>{meeting.title || "Untitled Meeting"}</h3>
                        <p className={styles.projDesc}>
                          {meeting.platform?.toUpperCase()} · {meeting.duration_seconds ? `${Math.round(meeting.duration_seconds / 60)}m` : "—"}
                        </p>
                        <div className={styles.projFooter}>
                          <span>
                            {meeting.started_at ? new Date(meeting.started_at).toLocaleDateString() : "—"}
                          </span>
                          <ArrowRight size={14} className={styles.arrow} />
                        </div>
                      </Card>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* ═══ TOPICS ═══ */}
            {activeSubTab === "topics" && (
              <div className={styles.topics}>
                {filteredTopics.length === 0 ? (
                  <div className={styles.emptyState}>
                    <Tag size={36} />
                    <p>No topics extracted yet. Topics are generated automatically from meeting summaries.</p>
                  </div>
                ) : (
                  <div className={styles.topicsCloud}>
                    {filteredTopics.map((topic: any) => (
                      <div key={topic.name} className={clsx(
                        styles.topicNode,
                        topic.severity === "high" ? styles.nodeHigh :
                          topic.severity === "medium" ? styles.nodeMedium : styles.nodeLow
                      )}>
                        <div className={styles.topicNodeMain}>
                          <Tag size={12} className={styles.tagIcon} />
                          <span>{topic.name}</span>
                          <span className={styles.topicBadge}>{topic.count}</span>
                        </div>
                        <span className={styles.topicNodeMeta}>Active: {topic.last_used}</span>
                      </div>
                    ))}
                  </div>
                )}

                {/* Decisions Timeline */}
                {filteredDecisions.length > 0 && (
                  <Card className={styles.timelineCard}>
                    <div className={styles.timelineHeader}>
                      <Sparkles size={16} className={styles.sparkleIcon} />
                      <h3>Decisions Timeline</h3>
                    </div>
                    <div className={styles.timeline}>
                      {filteredDecisions.map((d: any, i: number) => (
                        <div key={i} className={styles.timelineItem}>
                          <div className={styles.timelineDot} />
                          <div className={styles.timelineMeta}>
                            <span className={styles.timelineDate}>
                              {d.meeting_date ? new Date(d.meeting_date).toLocaleDateString("en-US", { weekday: "long", month: "short", day: "numeric" }) : "—"}
                              {d.meeting_title && ` • ${d.meeting_title}`}
                            </span>
                            <p>{d.decision}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </Card>
                )}
              </div>
            )}

            {/* ═══ PEOPLE ═══ */}
            {activeSubTab === "people" && (
              <div className={styles.people}>
                {filteredPeople.length === 0 ? (
                  <div className={styles.emptyState}>
                    <Users size={36} />
                    <p>No speaker profiles yet. They are built automatically from meeting transcripts.</p>
                  </div>
                ) : (
                  <div className={styles.peopleGrid}>
                    {filteredPeople.map((person: any) => (
                      <Card key={person.name} className={styles.peopleCard}>
                        <Avatar name={person.name} size="lg" />
                        <h3 className={styles.personName}>{person.name}</h3>
                        <div className={styles.personStats}>
                          <div className={styles.personStatItem}>
                            <span>Meetings</span>
                            <strong>{person.meeting_count}</strong>
                          </div>
                          <div className={styles.personStatItem}>
                            <span>Talk Time</span>
                            <strong>{person.talk_minutes}m</strong>
                          </div>
                          <div className={styles.personStatItem}>
                            <span>Words</span>
                            <strong>{(person.word_count || 0).toLocaleString()}</strong>
                          </div>
                        </div>
                      </Card>
                    ))}
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
};

export default Knowledge;
