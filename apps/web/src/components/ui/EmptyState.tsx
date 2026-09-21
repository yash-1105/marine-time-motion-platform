'use client'

import React from 'react'

export interface EmptyStateProps {
  title: string
  description?: string
  icon?: React.ReactNode
  action?: React.ReactNode
  className?: string
}

/** For an empty result set — not for missing/uncomputable data, which should use StatusBadge tone="neutral" inline instead. */
export const EmptyState: React.FC<EmptyStateProps> = ({ title, description, icon, action, className = '' }) => (
  <div className={`flex flex-col items-center justify-center text-center py-16 px-6 text-[var(--color-text-secondary)] ${className}`}>
    {icon && <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface-muted)] text-xl text-[var(--color-accent)]">{icon}</div>}
    <p className="text-sm font-semibold text-[var(--color-text-primary)]">{title}</p>
    {description && <p className="text-xs leading-5 mt-1.5 max-w-md">{description}</p>}
    {action && <div className="mt-4">{action}</div>}
  </div>
)
