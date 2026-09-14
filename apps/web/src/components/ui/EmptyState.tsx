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
  <div className={`flex flex-col items-center justify-center text-center py-14 px-6 text-[var(--color-text-secondary)] ${className}`}>
    {icon && <div className="mb-3 text-3xl opacity-60">{icon}</div>}
    <p className="text-sm font-medium text-[var(--color-text-primary)]">{title}</p>
    {description && <p className="text-xs mt-1 max-w-sm">{description}</p>}
    {action && <div className="mt-4">{action}</div>}
  </div>
)
