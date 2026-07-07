import React, { useRef, useState, useEffect } from "react";
import { LineChart, Line } from "recharts";

interface SparkLineProps {
  data: number[];
  color?: string;
  width?: number | string;
  height?: number;
}

export const SparkLine: React.FC<SparkLineProps> = React.memo(({
  data,
  color = "#6366f1",
  width = "100%",
  height = 30,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [resolvedWidth, setResolvedWidth] = useState(120);

  useEffect(() => {
    if (!containerRef.current) return;
    const obs = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const w = Math.floor(entry.contentRect.width);
        if (w > 0) setResolvedWidth(w);
      }
    });
    obs.observe(containerRef.current);
    return () => obs.disconnect();
  }, []);

  const chartData = data.map((val, idx) => ({ index: idx, value: val }));

  return (
    <div ref={containerRef} style={{ width, height: height, display: "inline-block" }}>
      <LineChart
        width={resolvedWidth}
        height={height}
        data={chartData}
        margin={{ top: 2, right: 2, left: 2, bottom: 2 }}
      >
        <Line
          type="monotone"
          dataKey="value"
          stroke={color}
          strokeWidth={1.5}
          dot={false}
        />
      </LineChart>
    </div>
  );
});

SparkLine.displayName = "SparkLine";
export default SparkLine;
