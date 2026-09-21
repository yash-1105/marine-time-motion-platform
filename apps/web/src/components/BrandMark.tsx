import React from 'react'

/** Compact wave-and-course mark: maritime movement resolved into a measured path. */
export function BrandMark({ className = '' }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 28 28"
      role="img"
      aria-label="Marine Time & Motion"
      className={className}
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <rect x="1" y="1" width="26" height="26" rx="7" fill="var(--color-accent-soft)" />
      <path d="M7 17.5c2.1 0 2.1-1.7 4.2-1.7s2.1 1.7 4.2 1.7 2.1-1.7 4.2-1.7" stroke="var(--color-accent)" strokeWidth="1.8" strokeLinecap="round" />
      <path d="M8.4 13.2h10.8l-2.4-4H11l-2.6 4Z" stroke="var(--color-accent)" strokeWidth="1.6" strokeLinejoin="round" />
      <path d="M14 6.2v3" stroke="var(--color-accent)" strokeWidth="1.6" strokeLinecap="round" />
      <circle cx="14" cy="6" r="1.25" fill="var(--color-accent)" />
      <path d="M7.5 21h13" stroke="var(--color-accent)" strokeWidth="1.5" strokeLinecap="round" opacity=".55" />
    </svg>
  )
}
