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
    className={`bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg shadow-[0_1px_2px_rgba(15,23,42,0.04)] ${
      padded ? 'p-5' : ''
    } ${className}`}
  >
    {children}
  </div>
)
