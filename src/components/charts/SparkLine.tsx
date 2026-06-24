import React from "react";
import { ResponsiveContainer, LineChart, Line } from "recharts";

interface SparkLineProps {
  data: number[];
  color?: string;
  width?: number | string;
  height?: number;
}

export const SparkLine: React.FC<SparkLineProps> = ({
  data,
  color = "#6366f1",
  width = "100%",
  height = 30,
}) => {
  const chartData = data.map((val, idx) => ({ index: idx, value: val }));

  return (
    <div style={{ width, height, display: "inline-block" }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartData} margin={{ top: 2, right: 2, left: 2, bottom: 2 }}>
          <Line
            type="monotone"
            dataKey="value"
            stroke={color}
            strokeWidth={1.5}
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
};
export default SparkLine;
