import React, { useRef, useState, useEffect } from "react";
import {
  AreaChart as RechartsAreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from "recharts";

interface DataItem {
  name: string;
  value: number;
}

interface AreaChartProps {
  data: DataItem[];
  color?: string;
  gradientId?: string;
  height?: number;
}

export const AreaChart: React.FC<AreaChartProps> = React.memo(({
  data,
  color = "#6366f1",
  gradientId = "area-glow",
  height = 150,
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
      <RechartsAreaChart
        width={width}
        height={height}
        data={data}
        margin={{ top: 10, right: 10, left: -20, bottom: 0 }}
      >
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor={color} stopOpacity={0.3} />
            <stop offset="95%" stopColor={color} stopOpacity={0.0} />
          </linearGradient>
        </defs>
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
        <Area
          type="monotone"
          dataKey="value"
          stroke={color}
          strokeWidth={2}
          fillOpacity={1}
          fill={`url(#${gradientId})`}
        />
      </RechartsAreaChart>
    </div>
  );
});

AreaChart.displayName = "AreaChart";
