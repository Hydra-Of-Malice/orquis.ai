import React, { useState, useMemo } from "react";
import styles from "./ContributionGrid.module.css";
import clsx from "clsx";

interface ContributionGridProps {
  defaultTimeframe?: string;
}

interface GridCell {
  id: number;
  level: 0 | 1 | 2 | 3 | 4;
  dateStr?: string;
  count: number;
}

export const ContributionGrid: React.FC<ContributionGridProps> = () => {
  const [selectedCell, setSelectedCell] = useState<GridCell | null>(null);
  const [year, setYear] = useState<number>(2026);

  const config = useMemo(() => {
    const contributionsMap: Record<number, number> = {
      2026: 842,
      2025: 718,
      2024: 593,
    };
    return {
      cols: 53, // Single year columns
      rows: 7,
      totalContributions: contributionsMap[year] || 842,
      label: `contributions in ${year}`,
      days: ["", "Mon", "", "Wed", "", "Fri", ""],
    };
  }, [year]);

  // Generate grid cells dynamically with randomized seed data based on selected year
  const gridCells = useMemo(() => {
    const totalCells = config.cols * config.rows;
    const cells: GridCell[] = [];

    // Simple deterministic randomizer based on idx and year
    const getRandomLevel = (idx: number): 0 | 1 | 2 | 3 | 4 => {
      const seed = Math.sin(idx + (year - 2010)) * 10000;
      const val = seed - Math.floor(seed);
      if (val > 0.9) return 4;
      if (val > 0.72) return 3;
      if (val > 0.5) return 2;
      if (val > 0.25) return 1;
      return 0;
    };

    for (let i = 0; i < totalCells; i++) {
      const level = getRandomLevel(i);
      const count = level === 0 ? 0 : level === 1 ? Math.floor(1 + Math.random() * 2) : level === 2 ? Math.floor(3 + Math.random() * 2) : level === 3 ? Math.floor(5 + Math.random() * 3) : Math.floor(8 + Math.random() * 4);
      cells.push({
        id: i,
        level,
        count,
      });
    }
    return cells;
  }, [config, year]);

  const monthPositions = [
    { name: "Jun", col: 1 },
    { name: "Jul", col: 5 },
    { name: "Aug", col: 10 },
    { name: "Sep", col: 14 },
    { name: "Oct", col: 18 },
    { name: "Nov", col: 23 },
    { name: "Dec", col: 27 },
    { name: "Jan", col: 31 },
    { name: "Feb", col: 36 },
    { name: "Mar", col: 40 },
    { name: "Apr", col: 45 },
    { name: "May", col: 49 },
  ];

  const startRowOffset = 2;

  return (
    <div className={styles.contributionGridWrapper}>
      {/* Heatmap header card panel */}
      <div className={styles.heatmapHeader}>
        <div className={styles.headerLeft}>
          <span className={styles.totalContributionsText}>
            {config.totalContributions} {config.label}
          </span>
          <span className={styles.contributionSettingsLink}>
            Contribution settings ▾
          </span>
        </div>
        
        {/* Dynamic Year Selector dropdown */}
        <div className={styles.yearSelectorContainer}>
          <label className={styles.yearLabel}>Select Year:</label>
          <select
            value={year}
            onChange={(e) => {
              setYear(Number(e.target.value));
              setSelectedCell(null);
            }}
            className={styles.yearSelect}
          >
            <option value={2026}>2026</option>
            <option value={2025}>2025</option>
            <option value={2024}>2024</option>
          </select>
        </div>
      </div>

      {/* Unified grid container without scrollbars, scaling dynamically */}
      <div className={styles.gridOuterContainer}>
        <div
          className={styles.unifiedGrid}
          style={{
            gridTemplateColumns: `24px repeat(${config.cols}, minmax(0, 1fr))`,
            gridTemplateRows: `20px repeat(7, minmax(0, 1fr))`,
          }}
        >
          {/* Month Headers */}
          {monthPositions.map((m, idx) => (
            <span
              key={`month-${idx}`}
              className={styles.monthLabelGrid}
              style={{ gridColumnStart: 1 + m.col, gridRowStart: 1 }}
            >
              {m.name}
            </span>
          ))}

          {/* Day Axis Labels (Mon, Wed, Fri) */}
          {config.days.map((day, idx) => {
            if (!day) return null;
            return (
              <span
                key={`day-${idx}`}
                className={styles.dayLabelGrid}
                style={{ gridColumnStart: 1, gridRowStart: startRowOffset + idx }}
              >
                {day}
              </span>
            );
          })}

          {/* Grid Squares */}
          {gridCells.map((cell, idx) => {
            const col = 2 + (idx % config.cols);
            const row = startRowOffset + Math.floor(idx / config.cols);
            return (
              <div
                key={cell.id}
                className={clsx(
                  styles.squareCell,
                  styles[`level${cell.level}`],
                  selectedCell?.id === cell.id && styles.squareSelected
                )}
                style={{ gridColumnStart: col, gridRowStart: row }}
                title={`${cell.count === 0 ? "No" : cell.count} contributions`}
                onClick={() => setSelectedCell(cell)}
              />
            );
          })}
        </div>
      </div>

      {/* Heatmap Footer Legend */}
      <div className={styles.heatmapFooter}>
        <span className={styles.footerLink}>
          Learn how we count contributions
        </span>
        
        <div className={styles.legendContainer}>
          <span className={styles.legendLabel}>Less</span>
          <div className={styles.legendSquares}>
            <div className={clsx(styles.squareCell, styles.level0)} style={{ width: "10px", height: "10px" }} />
            <div className={clsx(styles.squareCell, styles.level1)} style={{ width: "10px", height: "10px" }} />
            <div className={clsx(styles.squareCell, styles.level2)} style={{ width: "10px", height: "10px" }} />
            <div className={clsx(styles.squareCell, styles.level3)} style={{ width: "10px", height: "10px" }} />
            <div className={clsx(styles.squareCell, styles.level4)} style={{ width: "10px", height: "10px" }} />
          </div>
          <span className={styles.legendLabel}>More</span>
        </div>
      </div>

      {/* Selected cell tooltip details */}
      {selectedCell && (
        <div className={styles.cellDetailsOverlay}>
          <span>
            Selected cell: <strong>{selectedCell.count} meetings/contributions</strong> recorded. Activity level: Level {selectedCell.level}/4.
          </span>
          <button className={styles.closeOverlayBtn} onClick={() => setSelectedCell(null)}>
            ✕
          </button>
        </div>
      )}
    </div>
  );
};

export default ContributionGrid;
