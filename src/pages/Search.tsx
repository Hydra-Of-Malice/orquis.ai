import React, { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../services/api";
import { PageHeader } from "../components/layout/PageHeader";
import { Card } from "../components/ui/Card";
import { Badge } from "../components/ui/Badge";
import { EmptyState } from "../components/ui/EmptyState";
import {
  Search as SearchIcon, Calendar, CheckSquare, MessageSquare,
  Play, Award, ChevronRight, Sparkles, X, Loader2
} from "lucide-react";
import styles from "./Search.module.css";
import clsx from "clsx";

export const Search: React.FC = () => {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [debouncedQ, setDebouncedQ] = useState("");
  const [filters, setFilters] = useState({
    meetings: true,
    transcripts: true,
    actionItems: true,
    decisions: true,
  });

  // Saved recent searches in sessionStorage
  const [recentSearches, setRecentSearches] = useState<string[]>(() => {
    try { return JSON.parse(sessionStorage.getItem("zapper_recent_searches") || "[]"); }
    catch { return []; }
  });

  const debounceRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const handleQueryChange = (val: string) => {
    setQuery(val);
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setDebouncedQ(val);
      if (val.trim().length >= 2) {
        const updated = [val, ...recentSearches.filter(s => s !== val)].slice(0, 8);
        setRecentSearches(updated);
        sessionStorage.setItem("zapper_recent_searches", JSON.stringify(updated));
      }
    }, 400);
  };

  // Real backend search
  const { data: results, isLoading, isFetching } = useQuery({
    queryKey: ["search", debouncedQ],
    queryFn: () => api.get(`/search?q=${encodeURIComponent(debouncedQ)}`).then(r => r.data),
    enabled: debouncedQ.trim().length >= 2,
    staleTime: 10000,
  });

  const meetings = (results?.meetings || []).filter(() => filters.meetings);
  const transcripts = (results?.transcripts || []).filter(() => filters.transcripts);
  const actionItems = (results?.action_items || []).filter(() => filters.actionItems);
  const decisions = (results?.decisions || []).filter(() => filters.decisions);

  const totalResults = meetings.length + transcripts.length + actionItems.length + decisions.length;
  const searching = isLoading || isFetching;

  const clearSearch = () => {
    setQuery("");
    setDebouncedQ("");
  };

  return (
    <div className={styles.container}>
      <PageHeader breadcrumbs={["Search", "Global"]} />

      <div className={styles.content}>
        {/* Search Box */}
        <div className={`${styles.searchBox} glass-card`}>
          <SearchIcon size={20} className={styles.searchIcon} />
          <input
            className={styles.searchInput}
            type="text"
            placeholder="Search meetings, transcripts, action items, decisions..."
            value={query}
            onChange={(e) => handleQueryChange(e.target.value)}
            autoFocus
          />
          {searching && <Loader2 size={18} className={styles.spinIcon} />}
          {query && !searching && (
            <button className={styles.clearBtn} onClick={clearSearch}><X size={16} /></button>
          )}
        </div>

        {/* Filter Pills */}
        <div className={styles.filterRow}>
          {[
            { key: "meetings", label: "Meetings", icon: <Calendar size={13} /> },
            { key: "transcripts", label: "Transcripts", icon: <MessageSquare size={13} /> },
            { key: "actionItems", label: "Action Items", icon: <CheckSquare size={13} /> },
            { key: "decisions", label: "Decisions", icon: <Award size={13} /> },
          ].map(({ key, label, icon }) => (
            <button
              key={key}
              className={clsx(styles.filterPill, filters[key as keyof typeof filters] && styles.pillActive)}
              onClick={() => setFilters(f => ({ ...f, [key]: !f[key as keyof typeof f] }))}
            >
              {icon} {label}
            </button>
          ))}
          {debouncedQ && (
            <span className={styles.resultCount}>
              {searching ? "Searching..." : `${totalResults} result${totalResults !== 1 ? "s" : ""}`}
            </span>
          )}
        </div>

        {/* Recent Searches (when no query) */}
        {!debouncedQ && recentSearches.length > 0 && (
          <Card className={styles.recentCard}>
            <div className={styles.recentHeader}>
              <Sparkles size={14} />
              <span>Recent Searches</span>
            </div>
            <div className={styles.recentList}>
              {recentSearches.map((s) => (
                <button key={s} className={styles.recentChip} onClick={() => { setQuery(s); setDebouncedQ(s); }}>
                  {s}
                </button>
              ))}
            </div>
          </Card>
        )}

        {/* No results */}
        {debouncedQ && !searching && totalResults === 0 && (
        <div className={styles.emptyState}>
          <SearchIcon size={32} style={{ opacity: 0.3 }} />
          <p>No results found for <em>"{debouncedQ}"</em>. Try a different term.</p>
        </div>
        )}

        {/* ═══ Meetings ═══ */}
        {meetings.length > 0 && (
          <div className={styles.section}>
            <div className={styles.sectionHeader}>
              <Calendar size={15} />
              <h3>Meetings</h3>
              <Badge className="badge-gray">{meetings.length}</Badge>
            </div>
            {meetings.map((m: any) => (
              <Card key={m.id} className={styles.resultCard} interactive onClick={() => navigate(`/meetings/${m.id}`)}>
                <div className={styles.resultMain}>
                  <Play size={14} className={styles.resultIcon} />
                  <div className={styles.resultBody}>
                    <strong>{m.title}</strong>
                    <span className={styles.resultMeta}>
                      {m.platform?.toUpperCase()} · {m.started_at ? new Date(m.started_at).toLocaleDateString() : "—"}
                    </span>
                  </div>
                </div>
                <ChevronRight size={14} className={styles.chevron} />
              </Card>
            ))}
          </div>
        )}

        {/* ═══ Transcripts ═══ */}
        {transcripts.length > 0 && (
          <div className={styles.section}>
            <div className={styles.sectionHeader}>
              <MessageSquare size={15} />
              <h3>Transcripts</h3>
              <Badge className="badge-gray">{transcripts.length}</Badge>
            </div>
            {transcripts.map((t: any) => (
              <Card key={t.id} className={styles.resultCard} interactive onClick={() => navigate(`/meetings/${t.meeting_id}`)}>
                <div className={styles.resultMain}>
                  <MessageSquare size={14} className={styles.resultIcon} />
                  <div className={styles.resultBody}>
                    <strong>{t.speaker}</strong>
                    <p className={styles.resultSnippet}>"{t.text}"</p>
                    <span className={styles.resultMeta}>{t.meeting_title} · {t.time}</span>
                  </div>
                </div>
                <ChevronRight size={14} className={styles.chevron} />
              </Card>
            ))}
          </div>
        )}

        {/* ═══ Action Items ═══ */}
        {actionItems.length > 0 && (
          <div className={styles.section}>
            <div className={styles.sectionHeader}>
              <CheckSquare size={15} />
              <h3>Action Items</h3>
              <Badge className="badge-gray">{actionItems.length}</Badge>
            </div>
            {actionItems.map((a: any) => (
              <Card key={a.id} className={styles.resultCard} interactive onClick={() => navigate("/tasks")}>
                <div className={styles.resultMain}>
                  <CheckSquare size={14} className={styles.resultIcon} />
                  <div className={styles.resultBody}>
                    <strong>{a.title}</strong>
                    <span className={styles.resultMeta}>
                      {a.assignee_name || "Unassigned"} · {a.priority} · {a.due_date || "No due date"}
                    </span>
                  </div>
                </div>
                <Badge className={a.status === "done" ? "badge-emerald" : "badge-gray"}>{a.status}</Badge>
              </Card>
            ))}
          </div>
        )}

        {/* ═══ Decisions ═══ */}
        {decisions.length > 0 && (
          <div className={styles.section}>
            <div className={styles.sectionHeader}>
              <Award size={15} />
              <h3>Decisions</h3>
              <Badge className="badge-gray">{decisions.length}</Badge>
            </div>
            {decisions.map((d: any, i: number) => (
              <Card key={i} className={styles.resultCard} interactive onClick={() => navigate(`/meetings/${d.meeting_id}`)}>
                <div className={styles.resultMain}>
                  <Award size={14} className={styles.resultIcon} />
                  <div className={styles.resultBody}>
                    <strong>{d.decision}</strong>
                    <span className={styles.resultMeta}>{d.meeting_title}</span>
                  </div>
                </div>
                <ChevronRight size={14} className={styles.chevron} />
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default Search;
