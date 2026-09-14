'use client'

import React, { useState, useEffect, useCallback } from 'react'
import { useRouter, useSearchParams, usePathname } from 'next/navigation'
import { FilterChip, FilterField } from './ui/FilterChip'

export interface FilterState {
  startDate: string
  endDate: string
  vesselType: string
  cargoType: string
  qualityStatus: string
}

const DEFAULT_FILTERS: FilterState = {
  startDate: '',
  endDate: '',
  vesselType: '',
  cargoType: '',
  qualityStatus: '',
}

function readFiltersFromParams(searchParams: URLSearchParams): FilterState {
  return {
    startDate: searchParams.get('startDate') || '',
    endDate: searchParams.get('endDate') || '',
    vesselType: searchParams.get('vesselType') || '',
    cargoType: searchParams.get('cargoType') || '',
    qualityStatus: searchParams.get('qualityStatus') || '',
  }
}

export const GlobalFilterBar: React.FC = () => {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()

  const [filters, setFilters] = useState<FilterState>(() => readFiltersFromParams(searchParams))
  const [isExpanded, setIsExpanded] = useState(false)

  // Sync state when URL search parameters change externally
  useEffect(() => {
    setFilters(readFiltersFromParams(searchParams))
  }, [searchParams])

  const applyFilters = useCallback(
    (newFilters: FilterState) => {
      const params = new URLSearchParams(searchParams.toString())
      Object.entries(newFilters).forEach(([key, val]) => {
        if (val) {
          params.set(key, val)
        } else {
          params.delete(key)
        }
      })
      router.push(`${pathname}?${params.toString()}`)
    },
    [router, pathname, searchParams]
  )

  const handleChange = (key: keyof FilterState, val: string) => {
    const updated = { ...filters, [key]: val }
    setFilters(updated)
    applyFilters(updated)
  }

  const handleReset = () => {
    setFilters(DEFAULT_FILTERS)
    applyFilters(DEFAULT_FILTERS)
  }

  const activeFilterCount = Object.values(filters).filter(Boolean).length

  return (
    <div className="bg-[var(--color-surface)] border-b border-[var(--color-border)] px-6 py-2.5 flex-shrink-0">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        {/* Left: Quick Summary & Key Filters */}
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs font-semibold uppercase tracking-wide text-[var(--color-text-tertiary)] flex items-center gap-1.5 mr-1">
            <span className="inline-block w-1.5 h-1.5 rounded-full bg-[var(--color-accent)]" aria-hidden="true" />
            Scope
          </span>

          <FilterChip
            ariaLabel="Filter by Vessel Type"
            value={filters.vesselType}
            onChange={(v) => handleChange('vesselType', v)}
            allLabel="All Vessel Types"
            options={[
              { value: 'Fully Cellular Containership', label: 'Fully Cellular Containership' },
              { value: 'Bulk Carrier', label: 'Bulk Carrier' },
              { value: 'Product Tanker', label: 'Product Tanker' },
              { value: 'General Cargo', label: 'General Cargo' },
              { value: 'Vehicle Carrier', label: 'Vehicle Carrier' },
              { value: 'Passenger (Cruise)', label: 'Passenger (Cruise)' },
            ]}
          />

          <FilterChip
            ariaLabel="Filter by Cargo Type"
            value={filters.cargoType}
            onChange={(v) => handleChange('cargoType', v)}
            allLabel="All Cargo Types"
            options={[
              { value: 'Container', label: 'Container' },
              { value: 'Bulk', label: 'Bulk' },
              { value: 'Break Bulk', label: 'Break Bulk' },
              { value: 'Liquid Bulk', label: 'Liquid Bulk' },
              { value: 'RoRo', label: 'RoRo' },
              { value: 'Passengers', label: 'Passengers' },
            ]}
          />

          <FilterChip
            ariaLabel="Filter by Data Quality Status"
            value={filters.qualityStatus}
            onChange={(v) => handleChange('qualityStatus', v)}
            allLabel="All DQ Statuses"
            options={[
              { value: 'CLEAN', label: 'Clean' },
              { value: 'FLAGGED', label: 'Flagged' },
              { value: 'QUARANTINED', label: 'Quarantined' },
            ]}
          />
        </div>

        {/* Right: Expand Toggle & Reset */}
        <div className="flex items-center gap-2">
          {activeFilterCount > 0 && (
            <button
              onClick={handleReset}
              className="text-xs text-[var(--color-text-tertiary)] hover:text-[var(--color-text-primary)] underline cursor-pointer"
            >
              Clear ({activeFilterCount})
            </button>
          )}

          <button
            onClick={() => setIsExpanded(!isExpanded)}
            aria-expanded={isExpanded}
            className="px-2.5 py-1.5 bg-[var(--color-surface)] hover:bg-[var(--color-surface-muted)] text-[var(--color-text-secondary)] rounded-md border border-[var(--color-border)] text-xs flex items-center gap-1.5 cursor-pointer"
          >
            <span>More filters</span>
            {activeFilterCount > 0 && (
              <span className="px-1.5 py-0.5 rounded-full bg-[var(--color-accent-soft)] text-[var(--color-accent)] text-[10px] font-semibold">
                {activeFilterCount}
              </span>
            )}
            <span className="text-[10px]" aria-hidden="true">{isExpanded ? '▲' : '▼'}</span>
          </button>
        </div>
      </div>

      {/* Expanded Secondary Filters */}
      {isExpanded && (
        <div className="mt-3 pt-3 border-t border-[var(--color-border)] grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3">
          <FilterField label="Start Date">
            <input
              type="date"
              value={filters.startDate}
              onChange={(e) => handleChange('startDate', e.target.value)}
              className="w-full bg-[var(--color-surface)] border border-[var(--color-border)] text-[var(--color-text-primary)] text-xs rounded-md px-2.5 py-1.5 focus:ring-2 focus:ring-[var(--color-accent)] focus:outline-none"
            />
          </FilterField>

          <FilterField label="End Date">
            <input
              type="date"
              value={filters.endDate}
              onChange={(e) => handleChange('endDate', e.target.value)}
              className="w-full bg-[var(--color-surface)] border border-[var(--color-border)] text-[var(--color-text-primary)] text-xs rounded-md px-2.5 py-1.5 focus:ring-2 focus:ring-[var(--color-accent)] focus:outline-none"
            />
          </FilterField>
        </div>
      )}
    </div>
  )
}
