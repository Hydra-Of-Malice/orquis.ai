import React, { useState, useMemo } from "react";
import styles from "./ContributionGrid.module.css";
import clsx from "clsx";
import { useQuery } from '@tanstack/react-query';
import meetingsApi from '../../services/meetings';

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

  const { data: meetings = [] } = useQuery({
    queryKey: ['meetings-year', year],
    queryFn: () => meetingsApi.list({ 
      from_date: `${year}-01-01T00:00:00Z`, 
      to_date: `${year}-12-31T23:59:59Z`, 
      limit: 1000 
    }),
  });

  const config = useMemo(() => {
    return {
      cols: 53, // Single year columns
      rows: 7,
      totalContributions: meetings.length,
      label: `meetings in ${year}`,
      days: ["", "Mon", "", "Wed", "", "Fri", ""],
    };
  }, [year, meetings.length]);

  const { gridCells, monthPositions } = useMemo(() => {
    const cells: GridCell[] = [];
    const countMap: Record<string, number> = {};
    
    meetings.forEach((m: any) => {
      if (m.created_at) {
        const d = new Date(m.created_at).toISOString().split('T')[0];
        countMap[d] = (countMap[d] || 0) + 1;
      }
    });

    const yearStart = new Date(`${year}-01-01T12:00:00`);
    const dayOfWeek = yearStart.getDay(); // 0 is Sunday
    const startDate = new Date(yearStart);
    startDate.setDate(yearStart.getDate() - dayOfWeek);

    const computedMonthPositions = [];
    let lastMonth = -1;

    for (let c = 0; c < config.cols; c++) {
      const colDate = new Date(startDate);
      colDate.setDate(startDate.getDate() + c * 7);
      const currentMonth = colDate.getMonth();
      if (currentMonth !== lastMonth && colDate.getFullYear() === year) {
        computedMonthPositions.push({ name: colDate.toLocaleString('default', { month: 'short' }), col: c + 1 });
        lastMonth = currentMonth;
      }
    }

    // Cells are rendered row by row (all Sun, all Mon, etc)
    for (let r = 0; r < 7; r++) {
      for (let c = 0; c < config.cols; c++) {
        const date = new Date(startDate);
        date.setDate(startDate.getDate() + c * 7 + r);
        const dateStr = date.toISOString().split('T')[0];
        
        // Hide dates outside the year for a cleaner look if desired, but standard graphs show them.
        const count = countMap[dateStr] || 0;
        let level: 0 | 1 | 2 | 3 | 4 = 0;
        if (count >= 4) level = 4;
        else if (count === 3) level = 3;
        else if (count === 2) level = 2;
        else if (count === 1) level = 1;

        cells.push({
          id: r * config.cols + c,
          level,
          dateStr,
          count,
        });
      }
    }

    return { gridCells: cells, monthPositions: computedMonthPositions };
  }, [year, meetings, config.cols]);

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
                title={`${cell.dateStr}: ${cell.count === 0 ? "No" : cell.count} meetings`}
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
            Selected date (<strong>{selectedCell.dateStr}</strong>): <strong>{selectedCell.count} meetings</strong> recorded. Activity level: Level {selectedCell.level}/4.
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
