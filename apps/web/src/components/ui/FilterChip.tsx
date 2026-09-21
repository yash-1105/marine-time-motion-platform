'use client'

import React from 'react'

export interface FilterChipOption {
  value: string
  label: string
}

export interface FilterChipProps {
  ariaLabel: string
  value: string
  onChange: (value: string) => void
  options: FilterChipOption[]
  /** Label shown for the empty/"all" option, e.g. "All Terminals". Ignored if options already includes a value:"" entry. */
  allLabel?: string
  className?: string
}

/** Compact select-as-chip control used in the global filter bar's primary row. */
export const FilterChip: React.FC<FilterChipProps> = ({ ariaLabel, value, onChange, options, allLabel, className = '' }) => (
  <select
    value={value}
    onChange={(e) => onChange(e.target.value)}
    aria-label={ariaLabel}
    className={`min-h-9 bg-[var(--color-surface)] border border-[var(--color-border-strong)] text-[var(--color-text-primary)] text-xs font-medium rounded-[var(--radius-md)] px-3 py-2 hover:border-[var(--color-accent-soft-border)] focus:border-[var(--color-accent)] focus:outline-none cursor-pointer ${className}`}
  >
    {allLabel && <option value="">{allLabel}</option>}
    {options.map((opt) => (
      <option key={opt.value} value={opt.value}>
        {opt.label}
      </option>
    ))}
  </select>
)

export interface FilterFieldProps {
  label: string
  children: React.ReactNode
  className?: string
}

/** Labeled wrapper for a filter control in the filter bar's expanded secondary panel. */
export const FilterField: React.FC<FilterFieldProps> = ({ label, children, className = '' }) => (
  <div className={className}>
    <label className="block text-[10px] uppercase tracking-[0.06em] text-[var(--color-text-secondary)] font-semibold mb-1.5">
      {label}
    </label>
    {children}
  </div>
)
