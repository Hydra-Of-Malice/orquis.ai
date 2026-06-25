import React from "react";
import styles from "./Tabs.module.css";
import clsx from "clsx";

interface TabItem {
  id: string;
  label: string;
  icon?: React.ReactNode;
}

interface TabsProps {
  items: TabItem[];
  activeId: string;
  onChange: (id: string) => void;
  className?: string;
}

export const Tabs: React.FC<TabsProps> = ({
  items,
  activeId,
  onChange,
  className,
}) => {
  return (
    <div className={clsx(styles.tabsContainer, className)}>
      <div className={styles.tabList}>
        {items.map((item) => {
          const isActive = item.id === activeId;
          return (
            <button
              key={item.id}
              className={clsx(styles.tabBtn, isActive && styles.active)}
              onClick={() => onChange(item.id)}
            >
              {item.icon && <span className={styles.icon}>{item.icon}</span>}
              <span>{item.label}</span>
              {isActive && <div className={styles.activeIndicator} />}
            </button>
          );
        })}
      </div>
    </div>
  );
};
