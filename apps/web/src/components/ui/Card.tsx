'use client'

import React from 'react'

export interface CardProps {
  children: React.ReactNode
  className?: string
  /** Set false to remove default padding, e.g. when the card wraps an edge-to-edge table. */
  padded?: boolean
}

/** Generic white surface container with a subtle border — the base unit of the page layout. */
export const Card: React.FC<CardProps> = ({ children, className = '', padded = true }) => (
  <div
    className={`bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] shadow-[var(--shadow-xs)] ${
      padded ? 'p-5 lg:p-6' : ''
    } ${className}`}
  >
    {children}
  </div>
)
