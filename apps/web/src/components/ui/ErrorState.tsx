'use client'

import React from 'react'
import { StatusBadge } from './StatusBadge'

export interface ErrorStateProps {
  title?: string
  description?: string
  onRetry?: () => void
  className?: string
}

export const ErrorState: React.FC<ErrorStateProps> = ({
  title = 'Something went wrong',
  description,
  onRetry,
  className = '',
}) => (
  <div className={`flex flex-col items-center justify-center text-center py-14 px-6 ${className}`}>
    <div className="mb-3">
      <StatusBadge label="Error" tone="critical" />
    </div>
    <p className="text-sm font-medium text-[var(--color-text-primary)]">{title}</p>
    {description && <p className="text-xs mt-1 max-w-sm text-[var(--color-text-secondary)]">{description}</p>}
    {onRetry && (
      <button
        onClick={onRetry}
        className="mt-4 px-3 py-1.5 text-xs font-medium rounded-md border border-[var(--color-border-strong)] text-[var(--color-text-primary)] hover:bg-[var(--color-surface-muted)] cursor-pointer"
      >
        Retry
      </button>
    )}
  </div>
)
