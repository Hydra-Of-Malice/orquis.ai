import React, { useEffect, useState } from 'react';
import styles from './StatCard.module.css';
import { ArrowUpRight, ArrowDownRight } from 'lucide-react';

interface StatCardProps {
  title: string;
  value: number;
  formatter?: (v: number) => string;
  trend?: {
    value: number;
    isPositive: boolean;
    label?: string;
  };
  icon?: React.ReactNode;
  iconColor?: 'indigo' | 'emerald' | 'amber' | 'purple' | 'red' | 'teal';
  sparklineData?: number[];
  className?: string;
}

export const StatCard: React.FC<StatCardProps> = ({
  title,
  value,
  formatter = (v) => v.toLocaleString(),
  trend,
  icon,
  iconColor = 'indigo',
  sparklineData,
  className = '',
}) => {
  const [displayValue, setDisplayValue] = useState<number>(0);

  useEffect(() => {
    let start = 0;
    const end = value;
    if (end === 0) {
      setDisplayValue(0);
      return;
    }
    
    const duration = 1000; // 1s
    const startTime = performance.now();

    const isDecimal = value % 1 !== 0;

    const animate = (currentTime: number) => {
      const elapsed = currentTime - startTime;
      const progress = Math.min(elapsed / duration, 1);
      
      // Ease out quad
      const easeProgress = progress * (2 - progress);
      const current = start + (end - start) * easeProgress;
      
      setDisplayValue(isDecimal ? parseFloat(current.toFixed(1)) : Math.floor(current));

      if (progress < 1) {
        requestAnimationFrame(animate);
      } else {
        setDisplayValue(end);
      }
    };

    requestAnimationFrame(animate);
  }, [value]);

  // Sparkline SVG path helper
  const getSparklinePath = (data: number[]) => {
    if (!data || data.length < 2) return '';
    const width = 100;
    const height = 30;
    const padding = 2;
    const max = Math.max(...data);
    const min = Math.min(...data);
    const range = max - min === 0 ? 1 : max - min;
    
    const points = data.map((val, index) => {
      const x = (index / (data.length - 1)) * (width - padding * 2) + padding;
      const y = height - ((val - min) / range) * (height - padding * 2) - padding;
      return `${x},${y}`;
    });
    
    return `M ${points.join(' L ')}`;
  };

  return (
    <div className={`${styles.card} glass-card animate-scale-in ${className}`}>
      <div className={styles.header}>
        <span className={styles.title}>{title}</span>
        {icon && (
          <div className={`${styles.iconContainer} ${styles[iconColor]}`}>
            {icon}
          </div>
        )}
      </div>
      
      <div className={styles.body}>
        <div className={styles.valueContainer}>
          <span className={styles.value}>{formatter(displayValue)}</span>
          {trend && (
            <div className={`${styles.trendBadge} ${trend.isPositive ? styles.trendUp : styles.trendDown}`}>
              {trend.isPositive ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
              <span>{trend.value}%</span>
            </div>
          )}
        </div>

        {sparklineData && sparklineData.length > 0 && (
          <div className={styles.sparkline}>
            <svg width="100" height="30" viewBox="0 0 100 30">
              <path
                d={getSparklinePath(sparklineData)}
                fill="none"
                stroke={trend ? (trend.isPositive ? 'var(--emerald)' : 'var(--red)') : 'var(--indigo)'}
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </div>
        )}
      </div>
      {trend?.label && <div className={styles.footer}>{trend.label}</div>}
    </div>
  );
};
