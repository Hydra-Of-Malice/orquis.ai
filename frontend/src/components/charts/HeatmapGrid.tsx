import React from "react";
import styles from "./HeatmapGrid.module.css";
import clsx from "clsx";

interface HeatmapGridProps {
  weeksCount?: number;
}

export const HeatmapGrid: React.FC<HeatmapGridProps> = ({ weeksCount = 24 }) => {
  // Generate mock data for grid
  const days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  const gridCells = Array.from({ length: weeksCount * 7 }, (_, i) => {
    // Random activity level: 0 (none), 1 (light), 2 (medium), 3 (busy)
    const val = Math.random();
    let level = 0;
    if (val > 0.85) level = 3;
    else if (val > 0.65) level = 2;
    else if (val > 0.4) level = 1;
    return {
      id: i,
      level,
      count: level === 0 ? 0 : level === 1 ? Math.floor(1 + Math.random() * 2) : level === 2 ? Math.floor(3 + Math.random() * 2) : Math.floor(5 + Math.random() * 3),
    };
  });

  return (
    <div className={styles.container}>
      <div className={styles.daysColumn}>
        {days.map((day, idx) => (
          <span key={day} className={styles.dayLabel}>
            {idx % 2 === 1 ? day : ""}
          </span>
        ))}
      </div>
      <div
        className={styles.grid}
        style={{ gridTemplateColumns: `repeat(${weeksCount}, minmax(0, 1fr))` }}
      >
        {gridCells.map((cell) => (
          <div
            key={cell.id}
            className={clsx(styles.cell, styles[`level${cell.level}`])}
            title={`${cell.count} meetings`}
          />
        ))}
      </div>
    </div>
  );
};
export default HeatmapGrid;
