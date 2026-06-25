import React from "react";
import { ResponsiveContainer, RadarChart as RechartsRadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar } from "recharts";

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

export const RadarChart: React.FC<RadarChartProps> = ({
  data,
  color = "#6366f1",
  height = 200,
}) => {
  return (
    <div style={{ width: "100%", height }}>
      <ResponsiveContainer width="100%" height="100%">
        <RechartsRadarChart cx="50%" cy="50%" outerRadius="70%" data={data}>
          <PolarGrid stroke="var(--border)" />
          <PolarAngleAxis
            dataKey="subject"
            stroke="var(--text-subtle)"
            fontSize={10}
          />
          <PolarRadiusAxis
            angle={30}
            domain={[0, 100]}
            stroke="var(--text-muted)"
            fontSize={9}
            tick={false}
            axisLine={false}
          />
          <Radar
            name="Score"
            dataKey="value"
            stroke={color}
            fill={color}
            fillOpacity={0.25}
          />
        </RechartsRadarChart>
      </ResponsiveContainer>
    </div>
  );
};
