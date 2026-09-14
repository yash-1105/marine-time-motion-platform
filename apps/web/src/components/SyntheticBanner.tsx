'use client'

import React from 'react'

interface SyntheticBannerProps {
  isSynthetic: boolean
}

export const SyntheticBanner: React.FC<SyntheticBannerProps> = ({ isSynthetic }) => {
  if (!isSynthetic) {
    return null
  }

  return (
    <div
      role="alert"
      aria-label="Synthetic Data Warning"
      className="bg-amber-500 text-slate-950 px-4 py-2 text-xs font-bold tracking-wider uppercase text-center border-b border-amber-600 flex items-center justify-center gap-2 select-none shadow-inner"
    >
      <span className="inline-block px-1.5 py-0.5 bg-slate-950 text-amber-400 rounded text-[10px] font-black">
        SYNTHETIC
      </span>
      <span>
        DEMONSTRATION &amp; TEST ENVIRONMENT — GOVERNED SYNTHETIC DATASET LOADED — NOT PRODUCTION
      </span>
    </div>
  )
}
