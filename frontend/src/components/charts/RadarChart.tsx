import React, { useRef, useState, useEffect } from "react";
import {
  RadarChart as RechartsRadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
} from "recharts";

interface DataItem {
  subject: string;
  value: number;
  fullMark: number;
}

interface RadarChartProps {
  data: DataItem[];
  color?: string;
  height?: number;
}

export const RadarChart: React.FC<RadarChartProps> = React.memo(({
  data,
  color = "#6366f1",
  height = 200,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(200);

  useEffect(() => {
    if (!containerRef.current) return;
    // Set initial width from DOM
    const w = containerRef.current.clientWidth;
    if (w > 0) setWidth(w);

    const obs = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const cw = Math.floor(entry.contentRect.width);
        if (cw > 0) setWidth(cw);
      }
    });
    obs.observe(containerRef.current);
    return () => obs.disconnect();
  }, []);

  const size = Math.min(width, height);

  return (
    <div ref={containerRef} style={{ width: "100%", height, overflow: "visible" }}>
      <RechartsRadarChart
        width={width}
        height={height}
        cx="50%"
        cy="50%"
        outerRadius="60%"
        data={data}
        style={{ overflow: "visible" }}
      >
        <PolarGrid stroke="var(--border)" />
        <PolarAngleAxis
          dataKey="subject"
          tick={{ fill: "var(--text-subtle)", fontSize: 9 }}
        />
        <PolarRadiusAxis
          angle={30}
          domain={[0, 100]}
          tick={false}
          axisLine={false}
        />
        <Radar
          name="Score"
          dataKey="value"
          stroke={color}
          fill={color}
          fillOpacity={0.3}
        />
      </RechartsRadarChart>
    </div>
  );
});

RadarChart.displayName = "RadarChart";
