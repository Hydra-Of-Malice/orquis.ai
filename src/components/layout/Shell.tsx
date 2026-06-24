import React, { useState, useEffect } from "react";
import { Sidebar } from "./Sidebar";
import { CommandPalette } from "./CommandPalette";
import styles from "./Shell.module.css";

interface ShellProps {
  children: React.ReactNode;
}

export const Shell: React.FC<ShellProps> = ({ children }) => {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    const saved = localStorage.getItem("zapper-sidebar-collapsed");
    return saved === "true";
  });
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);

  useEffect(() => {
    localStorage.setItem("zapper-sidebar-collapsed", String(sidebarCollapsed));
  }, [sidebarCollapsed]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Toggle sidebar collapsed with `[`
      if (e.key === "[" && !(e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement)) {
        e.preventDefault();
        setSidebarCollapsed((prev) => !prev);
      }

      // Toggle command palette with `Ctrl+K` / `Cmd+K`
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setCommandPaletteOpen((prev) => !prev);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  return (
    <div className={styles.shell}>
      <Sidebar collapsed={sidebarCollapsed} setCollapsed={setSidebarCollapsed} />
      <div className={styles.mainContainer}>
        <main className={styles.mainContent}>
          {React.cloneElement(children as any, {
            onOpenCommandPalette: () => setCommandPaletteOpen(true),
          })}
        </main>
      </div>
      <CommandPalette isOpen={commandPaletteOpen} onClose={() => setCommandPaletteOpen(false)} />
    </div>
  );
};
export default Shell;
