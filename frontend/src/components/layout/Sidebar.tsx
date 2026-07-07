import React from "react";
import { NavLink } from "react-router-dom";
import { useTheme } from "../../context/ThemeContext";
import { useQuery } from "@tanstack/react-query";
import { meetingsApi } from "../../services/meetings";
import styles from "./Sidebar.module.css";
import {
  Home,
  Video,
  Calendar,
  Layers,
  Search,
  Lightbulb,
  FolderOpen,
  Users,
  CheckSquare,
  BarChart2,
  Cpu,
  Plug,
  Settings,
  ChevronLeft,
  ChevronRight,
  Sun,
  Moon,
  Zap,
} from "lucide-react";
import clsx from "clsx";

interface SidebarProps {
  collapsed: boolean;
  setCollapsed: (collapsed: boolean) => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ collapsed, setCollapsed }) => {
  const { theme, toggleTheme } = useTheme();

  const { data: rawMeetings = [] } = useQuery({
    queryKey: ["sidebar-meetings"],
    queryFn: () => meetingsApi.list({ limit: 100 }),
    refetchInterval: 5000,
  });

  const recordingsCount = rawMeetings.filter((m: any) => m.status === "done").length;

  const toggleCollapsed = () => setCollapsed(!collapsed);

  return (
    <aside className={clsx(styles.sidebar, collapsed && styles.collapsed)}>
      <div className={styles.header}>
        <div className={styles.logo}>
          <span className={styles.logoDot} />
          {!collapsed && <span className={styles.logoText}>Zapper</span>}
        </div>
        <button className={styles.collapseBtn} onClick={toggleCollapsed} title="Toggle Sidebar ( [ )">
          {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
        </button>
      </div>

      <nav className={styles.nav}>
        <div className={styles.section}>
          <NavLink
            to="/dashboard"
            end
            className={({ isActive }) => clsx(styles.link, isActive && styles.active)}
            title="Dashboard"
          >
            <Home size={18} />
            {!collapsed && <span>Home</span>}
          </NavLink>
        </div>

        <div className={styles.section}>
          {!collapsed && <div className={styles.sectionTitle}>Meetings</div>}
          <NavLink
            to="/meetings/live"
            className={({ isActive }) => clsx(styles.link, isActive && styles.active)}
            title="Live Meetings"
          >
            <span className={styles.liveIndicatorContainer}>
              <Video size={18} />
              <span className={styles.liveDot} />
            </span>
            {!collapsed && (
              <span className={styles.liveText}>
                Live <span className={styles.liveBadge}>REC</span>
              </span>
            )}
          </NavLink>
          <NavLink
            to="/meetings/upcoming"
            className={({ isActive }) => clsx(styles.link, isActive && styles.active)}
            title="Upcoming & Calendar"
          >
            <Calendar size={18} />
            {!collapsed && <span>Upcoming</span>}
          </NavLink>
          <NavLink
            to="/meetings/recordings"
            className={({ isActive }) => clsx(styles.link, isActive && styles.active)}
            title="Recordings Library"
          >
            <Layers size={18} />
            {!collapsed && (
              <span className={styles.justifyBetweenWrapper}>
                <span>Recordings</span>
                {recordingsCount > 0 && <span className={styles.countBadge}>{recordingsCount}</span>}
              </span>
            )}
          </NavLink>
        </div>

        <div className={styles.section}>
          {!collapsed && <div className={styles.sectionTitle}>Knowledge</div>}
          <NavLink
            to="/search"
            className={({ isActive }) => clsx(styles.link, isActive && styles.active)}
            title="Global Search"
          >
            <Search size={18} />
            {!collapsed && <span>Search</span>}
          </NavLink>
          <NavLink
            to="/knowledge/topics"
            className={({ isActive }) => clsx(styles.link, isActive && styles.active)}
            title="Topics Explorer"
          >
            <Lightbulb size={18} />
            {!collapsed && <span>Topics</span>}
          </NavLink>
          <NavLink
            to="/knowledge/projects"
            className={({ isActive }) => clsx(styles.link, isActive && styles.active)}
            title="Projects Directory"
          >
            <FolderOpen size={18} />
            {!collapsed && <span>Projects</span>}
          </NavLink>
          <NavLink
            to="/knowledge/people"
            className={({ isActive }) => clsx(styles.link, isActive && styles.active)}
            title="People Directory"
          >
            <Users size={18} />
            {!collapsed && <span>People</span>}
          </NavLink>
        </div>

        <div className={styles.section}>
          <NavLink
            to="/tasks"
            className={({ isActive }) => clsx(styles.link, isActive && styles.active)}
            title="Action Items"
          >
            <CheckSquare size={18} />
            {!collapsed && <span>Tasks</span>}
          </NavLink>
        </div>

        <div className={styles.section}>
          {!collapsed && <div className={styles.sectionTitle}>Analytics</div>}
          <NavLink
            to="/analytics/overview"
            className={({ isActive }) => clsx(styles.link, isActive && styles.active)}
            title="Overview Analytics"
          >
            <BarChart2 size={18} />
            {!collapsed && <span>Overview</span>}
          </NavLink>
          <NavLink
            to="/analytics/team"
            className={({ isActive }) => clsx(styles.link, isActive && styles.active)}
            title="Team Insights"
          >
            <Users size={18} />
            {!collapsed && <span>Team Insights</span>}
          </NavLink>
          <NavLink
            to="/analytics/coaching"
            className={({ isActive }) => clsx(styles.link, isActive && styles.active)}
            title="My Coaching (Private)"
          >
            <BarChart2 size={18} className={styles.coachingIcon} />
            {!collapsed && <span className={styles.coachingLabel}>My Coaching</span>}
          </NavLink>
        </div>

        <div className={styles.section}>
          <NavLink
            to="/automations"
            className={({ isActive }) => clsx(styles.link, isActive && styles.active)}
            title="Automations"
          >
            <Cpu size={18} />
            {!collapsed && <span>Automations</span>}
          </NavLink>
          <NavLink
            to="/integrations"
            className={({ isActive }) => clsx(styles.link, isActive && styles.active)}
            title="Integrations Catalog"
          >
            <Plug size={18} />
            {!collapsed && <span>Integrations</span>}
          </NavLink>
        </div>
      </nav>

      <div className={styles.footer}>
        <button
          className={styles.themeToggleBtn}
          onClick={toggleTheme}
          title={theme === "dark" ? "Switch to Light Mode" : "Switch to Dark Mode"}
        >
          {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
          {!collapsed && <span>{theme === "dark" ? "Light Mode" : "Dark Mode"}</span>}
        </button>
        <NavLink
          to="/settings"
          className={({ isActive }) => clsx(styles.settingsLink, isActive && styles.activeSettings)}
          title="Settings"
        >
          <Settings size={18} />
          {!collapsed && <span>Settings</span>}
        </NavLink>
      </div>
    </aside>
  );
};
