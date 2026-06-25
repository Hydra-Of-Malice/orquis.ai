import React, { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useAppStore } from "../../store/useAppStore";
import { useTheme } from "../../context/ThemeContext";
import styles from "./CommandPalette.module.css";
import { Search, Compass, Shield, Settings, FileText, Moon, Sun } from "lucide-react";
import clsx from "clsx";

interface CommandPaletteProps {
  isOpen: boolean;
  onClose: () => void;
}

interface CommandItem {
  id: string;
  category: "Navigation" | "Meetings" | "Actions";
  title: string;
  subtitle?: string;
  icon: React.ReactNode;
  action: () => void;
}

export const CommandPalette: React.FC<CommandPaletteProps> = ({ isOpen, onClose }) => {
  const navigate = useNavigate();
  const meetings = useAppStore((state) => state.meetings);
  const { theme, toggleTheme } = useTheme();
  const [search, setSearch] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isOpen) {
      setSearch("");
      setActiveIndex(0);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [isOpen]);

  const baseCommands: CommandItem[] = [
    {
      id: "nav_home",
      category: "Navigation",
      title: "Go to Dashboard / Home",
      icon: <Compass size={16} />,
      action: () => {
        navigate("/dashboard");
        onClose();
      },
    },
    {
      id: "nav_recs",
      category: "Navigation",
      title: "Go to Recordings Library",
      icon: <FileText size={16} />,
      action: () => {
        navigate("/meetings/recordings");
        onClose();
      },
    },
    {
      id: "nav_settings",
      category: "Navigation",
      title: "Go to Settings",
      icon: <Settings size={16} />,
      action: () => {
        navigate("/settings");
        onClose();
      },
    },
    {
      id: "act_theme",
      category: "Actions",
      title: `Switch to ${theme === "dark" ? "Light" : "Dark"} Mode`,
      icon: theme === "dark" ? <Sun size={16} /> : <Moon size={16} />,
      action: () => {
        toggleTheme();
        onClose();
      },
    },
  ];

  const meetingCommands: CommandItem[] = meetings.map((m) => ({
    id: `meet_${m.id}`,
    category: "Meetings",
    title: m.title,
    subtitle: `Meeting • ${m.status}`,
    icon: <Shield size={16} />,
    action: () => {
      if (m.status === "live") {
        navigate(`/live/${m.id}`);
      } else {
        navigate(`/meetings/${m.id}`);
      }
      onClose();
    },
  }));

  const allCommands = [...baseCommands, ...meetingCommands];

  const filteredCommands = allCommands.filter(
    (cmd) =>
      cmd.title.toLowerCase().includes(search.toLowerCase()) ||
      cmd.category.toLowerCase().includes(search.toLowerCase()) ||
      (cmd.subtitle && cmd.subtitle.toLowerCase().includes(search.toLowerCase()))
  );

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!isOpen) return;

      if (e.key === "ArrowDown") {
        e.preventDefault();
        setActiveIndex((prev) => (prev + 1) % filteredCommands.length);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setActiveIndex((prev) => (prev - 1 + filteredCommands.length) % filteredCommands.length);
      } else if (e.key === "Enter") {
        e.preventDefault();
        if (filteredCommands[activeIndex]) {
          filteredCommands[activeIndex].action();
        }
      } else if (e.key === "Escape") {
        onClose();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, activeIndex, filteredCommands, onClose]);

  if (!isOpen) return null;

  return (
    <div className={styles.overlay} onClick={onClose}>
      <div className={styles.dialog} onClick={(e) => e.stopPropagation()}>
        <div className={styles.searchBar}>
          <Search size={18} className={styles.searchIcon} />
          <input
            ref={inputRef}
            type="text"
            className={styles.input}
            placeholder="Type a command or search meetings..."
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setActiveIndex(0);
            }}
          />
          <span className={styles.escBadge}>ESC</span>
        </div>

        <div className={styles.results}>
          {filteredCommands.length > 0 ? (
            filteredCommands.map((cmd, index) => {
              const isActive = index === activeIndex;
              return (
                <div
                  key={cmd.id}
                  className={clsx(styles.item, isActive && styles.activeItem)}
                  onClick={cmd.action}
                  onMouseEnter={() => setActiveIndex(index)}
                >
                  <span className={styles.icon}>{cmd.icon}</span>
                  <div className={styles.meta}>
                    <span className={styles.title}>{cmd.title}</span>
                    {cmd.subtitle && <span className={styles.subtitle}>{cmd.subtitle}</span>}
                  </div>
                  <span className={styles.category}>{cmd.category}</span>
                </div>
              );
            })
          ) : (
            <div className={styles.noResults}>No matches found.</div>
          )}
        </div>
      </div>
    </div>
  );
};
