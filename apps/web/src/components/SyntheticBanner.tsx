'use client'

import React from 'react'

interface SyntheticBannerProps {
  isSynthetic: boolean
}

/**
 * Subtle, professional data-provenance disclosure.
 * Replaces the old full-width alarmist banner — provenance still discloses,
 * it just no longer dominates the interface.
 */
export const SyntheticBanner: React.FC<SyntheticBannerProps> = ({ isSynthetic }) => {
  if (!isSynthetic) {
    return null
  }

  return (
    <span
      className="inline-flex items-center gap-1.5 text-xs text-[var(--color-text-tertiary)]"
      title="This environment is loaded with a governed synthetic benchmark dataset, not production data."
    >
      <span className="inline-block w-1.5 h-1.5 rounded-full bg-[var(--color-accent)]" aria-hidden="true" />
      Dataset: Synthetic benchmark
    </span>
  )
}
