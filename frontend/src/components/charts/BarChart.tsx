import React, { useRef, useState, useEffect } from "react";
import {
  BarChart as RechartsBarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Cell,
} from "recharts";

interface DataItem {
  name: string;
  value: number;
}

interface BarChartProps {
  data: DataItem[];
  colors?: string[];
  height?: number;
}

export const BarChart: React.FC<BarChartProps> = React.memo(({
  data,
  colors = ["#6366f1", "#10b981", "#f59e0b", "#ef4444", "#a855f7"],
  height = 200,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(400);

  useEffect(() => {
    if (!containerRef.current) return;
    const obs = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const w = Math.floor(entry.contentRect.width);
        if (w > 0) setWidth(w);
      }
    });
    obs.observe(containerRef.current);
    return () => obs.disconnect();
  }, []);

  return (
    <div ref={containerRef} style={{ width: "100%", height }}>
      <RechartsBarChart
        width={width}
        height={height}
        data={data}
        margin={{ top: 10, right: 10, left: -20, bottom: 0 }}
      >
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
        <XAxis
          dataKey="name"
          stroke="var(--text-muted)"
          fontSize={11}
          tickLine={false}
          axisLine={false}
        />
        <YAxis
          stroke="var(--text-muted)"
          fontSize={11}
          tickLine={false}
          axisLine={false}
        />
        <Tooltip
          cursor={false}
          contentStyle={{
            background: "var(--card)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-xs)",
          }}
          itemStyle={{
            color: "var(--text)",
          }}
          labelStyle={{
            color: "var(--text-secondary)",
            fontWeight: 500,
            marginBottom: "4px",
          }}
        />
        <Bar dataKey="value" radius={[4, 4, 0, 0]}>
          {data.map((_, index) => (
            <Cell key={`cell-${index}`} fill={colors[index % colors.length]} />
          ))}
        </Bar>
      </RechartsBarChart>
    </div>
  );
});

BarChart.displayName = "BarChart";
