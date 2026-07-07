import React from "react";

interface DataItem {
  name: string;
  value: number;
}

interface DonutChartProps {
  data: DataItem[];
  colors?: string[];
  size?: number;
}

const DEFAULT_COLORS = ["#6366f1", "#10b981", "#f59e0b", "#ef4444", "#a855f7", "#14b8a6"];

function polarToCartesian(cx: number, cy: number, r: number, angleRad: number) {
  return {
    x: cx + r * Math.cos(angleRad),
    y: cy + r * Math.sin(angleRad),
  };
}

export const DonutChart: React.FC<DonutChartProps> = ({
  data,
  colors = DEFAULT_COLORS,
  size = 160,
}) => {
  if (!data || data.length === 0) return null;

  const total = data.reduce((s, d) => s + (d.value || 0), 0);
  if (total === 0) return null;

  const cx = size / 2;
  const cy = size / 2;
  const outerR = size * 0.4;
  const innerR = size * 0.25;
  const gapAngle = data.length > 1 ? 0.04 : 0;

  let startAngle = -Math.PI / 2;

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        style={{ flexShrink: 0, overflow: "visible" }}
      >
        {data.map((item, i) => {
          const sliceAngle = (item.value / total) * 2 * Math.PI - gapAngle;
          const endAngle = startAngle + sliceAngle;
          const color = colors[i % colors.length];

          const o1 = polarToCartesian(cx, cy, outerR, startAngle);
          const o2 = polarToCartesian(cx, cy, outerR, endAngle);
          const i1 = polarToCartesian(cx, cy, innerR, endAngle);
          const i2 = polarToCartesian(cx, cy, innerR, startAngle);
          const large = sliceAngle > Math.PI ? 1 : 0;

          const pathD = [
            `M ${o1.x} ${o1.y}`,
            `A ${outerR} ${outerR} 0 ${large} 1 ${o2.x} ${o2.y}`,
            `L ${i1.x} ${i1.y}`,
            `A ${innerR} ${innerR} 0 ${large} 0 ${i2.x} ${i2.y}`,
            "Z",
          ].join(" ");

          startAngle = endAngle + gapAngle;

          return <path key={i} d={pathD} fill={color} />;
        })}
      </svg>

      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {data.map((item, i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div
              style={{
                width: 10,
                height: 10,
                borderRadius: "50%",
                backgroundColor: colors[i % colors.length],
                flexShrink: 0,
              }}
            />
            <span style={{ fontSize: 12, color: "var(--text-subtle)", whiteSpace: "nowrap" }}>
              {item.name}&nbsp;
              <strong style={{ color: "var(--text)" }}>{item.value}%</strong>
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};
