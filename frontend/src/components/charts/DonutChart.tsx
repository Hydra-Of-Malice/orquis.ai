import React from "react";
import { ResponsiveContainer, PieChart, Pie, Cell, Tooltip } from "recharts";

interface DataItem {
  name: string;
  value: number;
}

interface DonutChartProps {
  data: DataItem[];
  colors?: string[];
  height?: number;
}

export const DonutChart: React.FC<DonutChartProps> = ({
  data,
  colors = ["#6366f1", "#10b981", "#f59e0b", "#ef4444", "#a855f7", "#14b8a6"],
  height = 200,
}) => {
  return (
    <div style={{ width: "100%", height }}>
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            innerRadius="60%"
            outerRadius="80%"
            paddingAngle={4}
            dataKey="value"
          >
            {data.map((_, index) => (
              <Cell key={`cell-${index}`} fill={colors[index % colors.length]} />
            ))}
          </Pie>
          <Tooltip
            contentStyle={{
              background: "var(--card)",
              border: "1px solid var(--border)",
              borderRadius: "var(--radius-xs)",
              color: "var(--text)",
            }}
          />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
};
