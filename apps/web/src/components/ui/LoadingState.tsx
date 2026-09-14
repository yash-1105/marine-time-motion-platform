'use client'

import React from 'react'

export interface LoadingStateProps {
  label?: string
  className?: string
}

export const LoadingState: React.FC<LoadingStateProps> = ({ label = 'Loading…', className = '' }) => (
  <div className={`flex flex-col items-center justify-center py-16 gap-3 text-[var(--color-text-secondary)] ${className}`}>
    <div
      className="h-6 w-6 rounded-full border-2 border-[var(--color-border-strong)] border-t-[var(--color-accent)] animate-spin motion-reduce:animate-none"
      role="status"
      aria-label={label}
    />
    <p className="text-xs">{label}</p>
  </div>
)
