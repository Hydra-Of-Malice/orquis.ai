import React from 'react';
import type { LucideIcon } from 'lucide-react';
import { Button } from './Button';

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description: string;
  actionText?: string;
  onAction?: () => void;
  className?: string;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  icon: Icon,
  title,
  description,
  actionText,
  onAction,
  className = '',
}) => {
  return (
    <div
      className={`flex flex-col align-center justify-between animate-fade-in ${className}`}
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '40px 20px',
        textAlign: 'center',
        background: 'var(--card)',
        border: '1px dashed var(--border)',
        borderRadius: 'var(--radius-lg)',
        maxWidth: '500px',
        margin: '20px auto',
        gap: '16px',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: '56px',
          height: '56px',
          borderRadius: 'var(--radius-full)',
          background: 'var(--bg-subtle)',
          color: 'var(--indigo)',
          border: '1px solid var(--border)',
        }}
      >
        <Icon size={26} />
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
        <h3 style={{ fontSize: '16px', fontWeight: 'var(--weight-semibold)', color: 'var(--text)' }}>
          {title}
        </h3>
        <p style={{ fontSize: '13px', color: 'var(--text-subtle)', maxWidth: '360px', lineHeight: '1.4' }}>
          {description}
        </p>
      </div>

      {actionText && onAction && (
        <Button onClick={onAction} variant="primary" size="sm" style={{ marginTop: '8px' }}>
          {actionText}
        </Button>
      )}
    </div>
  );
};
