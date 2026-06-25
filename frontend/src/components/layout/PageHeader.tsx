import React from "react";
import styles from "./PageHeader.module.css";
import { Search } from "lucide-react";

interface PageHeaderProps {
  breadcrumbs: string[];
  actions?: React.ReactNode;
  onOpenCommandPalette?: () => void;
}

export const PageHeader: React.FC<PageHeaderProps> = ({
  breadcrumbs,
  actions,
  onOpenCommandPalette,
}) => {
  const isMac = typeof window !== "undefined" && /Mac|iPod|iPhone|iPad/.test(navigator.platform);

  return (
    <header className={styles.header}>
      <div className={styles.left}>
        <div className={styles.breadcrumbs}>
          {breadcrumbs.map((crumb, index) => (
            <React.Fragment key={crumb}>
              {index > 0 && <span className={styles.separator}>/</span>}
              <span className={index === breadcrumbs.length - 1 ? styles.activeCrumb : styles.crumb}>
                {crumb}
              </span>
            </React.Fragment>
          ))}
        </div>
      </div>

      <div className={styles.right}>
        {onOpenCommandPalette && (
          <button className={styles.cmdPaletteBtn} onClick={onOpenCommandPalette} title="Open Command Palette">
            <Search size={14} />
            <span>Search / Commands</span>
            <kbd className={styles.kbd}>
              {isMac ? "⌘K" : "Ctrl+K"}
            </kbd>
          </button>
        )}
        {actions && <div className={styles.actions}>{actions}</div>}
      </div>
    </header>
  );
};
