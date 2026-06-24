import React from 'react';

interface ProgressRingProps {
  value: number;
  size?: number;
  strokeWidth?: number;
  color?: string; // CSS color string or var
  label?: string;
  showValue?: boolean;
}

export const ProgressRing: React.FC<ProgressRingProps> = ({
  value,
  size = 64,
  strokeWidth = 6,
  color = 'var(--indigo)',
  label,
  showValue = true,
}) => {
  const radius = (size - strokeWidth) / 2;
  const circumference = radius * 2 * Math.PI;
  const clampedValue = Math.max(0, Math.min(100, value));
  const offset = circumference - (clampedValue / 100) * circumference;

  return (
    <div className="flex flex-col align-center justify-between" style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
      <div style={{ position: 'relative', width: size, height: size }}>
        <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
          {/* Background circle */}
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="transparent"
            stroke="var(--border)"
            strokeWidth={strokeWidth}
          />
          {/* Progress circle */}
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="transparent"
            stroke={color}
            strokeWidth={strokeWidth}
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            strokeLinecap="round"
            style={{
              transition: 'stroke-dashoffset 0.8s ease-in-out',
            }}
          />
        </svg>
        {showValue && (
          <div
            style={{
              position: 'absolute',
              top: 0,
              left: 0,
              width: '100%',
              height: '100%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: `${Math.max(10, size / 4.5)}px`,
              fontWeight: 'var(--weight-semibold)',
              color: 'var(--text)',
            }}
          >
            {clampedValue}%
          </div>
        )}
      </div>
      {label && (
        <span style={{ fontSize: '11px', color: 'var(--text-subtle)', fontWeight: 'var(--weight-medium)', marginTop: '4px' }}>
          {label}
        </span>
      )}
    </div>
  );
};
