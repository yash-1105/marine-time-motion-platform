'use client'

import React from 'react'

export interface LoadingStateProps {
  label?: string
  className?: string
}

export const LoadingState: React.FC<LoadingStateProps> = ({ label = 'Loading…', className = '' }) => (
  <div className={`flex flex-col items-center justify-center py-20 gap-3.5 text-[var(--color-text-secondary)] ${className}`}>
    <div className="relative flex h-9 w-9 items-center justify-center rounded-[10px] bg-[var(--color-accent-soft)]">
      <div
      className="h-5 w-5 rounded-full border-2 border-[var(--color-accent-soft-border)] border-t-[var(--color-accent)] animate-spin motion-reduce:animate-none"
      role="status"
      aria-label={label}
      />
    </div>
    <p className="text-xs font-medium">{label}</p>
  </div>
)
