import React, { useState } from 'react';

interface TooltipProps {
  content: React.ReactNode;
  position?: 'top' | 'bottom' | 'left' | 'right';
  children: React.ReactNode;
}

export const Tooltip: React.FC<TooltipProps> = ({
  content,
  position = 'top',
  children,
}) => {
  const [isVisible, setIsVisible] = useState(false);

  const getPositionStyles = () => {
    switch (position) {
      case 'bottom':
        return {
          top: '100%',
          left: '50%',
          transform: 'translateX(-50%) translateY(6px)',
        };
      case 'left':
        return {
          top: '50%',
          right: '100%',
          transform: 'translateY(-50%) translateX(-6px)',
        };
      case 'right':
        return {
          top: '50%',
          left: '100%',
          transform: 'translateY(-50%) translateX(6px)',
        };
      case 'top':
      default:
        return {
          bottom: '100%',
          left: '50%',
          transform: 'translateX(-50%) translateY(-6px)',
        };
    }
  };

  return (
    <div
      style={{ display: 'inline-flex', position: 'relative' }}
      onMouseEnter={() => setIsVisible(true)}
      onMouseLeave={() => setIsVisible(false)}
    >
      {children}
      {isVisible && (
        <div
          style={{
            position: 'absolute',
            zIndex: 9999,
            backgroundColor: 'var(--bg-subtle)',
            color: 'var(--text)',
            border: '1px solid var(--border)',
            padding: '6px 10px',
            fontSize: '11px',
            fontWeight: 'var(--weight-medium)',
            borderRadius: 'var(--radius-sm)',
            boxShadow: 'var(--shadow-lg)',
            whiteSpace: 'nowrap',
            pointerEvents: 'none',
            ...getPositionStyles(),
          }}
          className="animate-scale-in"
        >
          {content}
        </div>
      )}
    </div>
  );
};
