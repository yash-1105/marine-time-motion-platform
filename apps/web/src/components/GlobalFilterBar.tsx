'use client'

import React, { useState, useEffect, useCallback } from 'react'
import { useRouter, useSearchParams, usePathname } from 'next/navigation'

export interface FilterState {
  startDate: string
  endDate: string
  port: string
  terminal: string
  berth: string
  vesselType: string
  movementType: string
  shippingLine: string
  vesselSize: string
  cargoType: string
  qualityStatus: string
}

const DEFAULT_FILTERS: FilterState = {
  startDate: '',
  endDate: '',
  port: '',
  terminal: '',
  berth: '',
  vesselType: '',
  movementType: '',
  shippingLine: '',
  vesselSize: '',
  cargoType: '',
  qualityStatus: '',
}

export const GlobalFilterBar: React.FC = () => {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()

  const [filters, setFilters] = useState<FilterState>(() => {
    return {
      startDate: searchParams.get('startDate') || '',
      endDate: searchParams.get('endDate') || '',
      port: searchParams.get('port') || '',
      terminal: searchParams.get('terminal') || '',
      berth: searchParams.get('berth') || '',
      vesselType: searchParams.get('vesselType') || '',
      movementType: searchParams.get('movementType') || '',
      shippingLine: searchParams.get('shippingLine') || '',
      vesselSize: searchParams.get('vesselSize') || '',
      cargoType: searchParams.get('cargoType') || '',
      qualityStatus: searchParams.get('qualityStatus') || '',
    }
  })

  const [isExpanded, setIsExpanded] = useState(false)

  // Sync state when URL search parameters change externally
  useEffect(() => {
    setFilters({
      startDate: searchParams.get('startDate') || '',
      endDate: searchParams.get('endDate') || '',
      port: searchParams.get('port') || '',
      terminal: searchParams.get('terminal') || '',
      berth: searchParams.get('berth') || '',
      vesselType: searchParams.get('vesselType') || '',
      movementType: searchParams.get('movementType') || '',
      shippingLine: searchParams.get('shippingLine') || '',
      vesselSize: searchParams.get('vesselSize') || '',
      cargoType: searchParams.get('cargoType') || '',
      qualityStatus: searchParams.get('qualityStatus') || '',
    })
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
    <div className="bg-slate-900 border-b border-slate-800 text-slate-300 text-xs px-4 py-2 flex-shrink-0">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        {/* Left: Quick Summary & Key Filters */}
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
            <span className="inline-block w-2 h-2 rounded-full bg-cyan-400"></span>
            Scope:
          </span>

          {/* Port */}
          <select
            value={filters.port}
            onChange={(e) => handleChange('port', e.target.value)}
            className="bg-slate-800 border border-slate-700 text-slate-200 text-xs rounded px-2 py-1 focus:ring-1 focus:ring-cyan-500 focus:outline-none"
            aria-label="Filter by Port"
          >
            <option value="">All Ports (ZADUR)</option>
            <option value="ZADUR">Durban (ZADUR)</option>
            <option value="ZACPT">Cape Town (ZACPT)</option>
            <option value="ZAPLZ">Port Elizabeth (ZAPLZ)</option>
          </select>

          {/* Terminal */}
          <select
            value={filters.terminal}
            onChange={(e) => handleChange('terminal', e.target.value)}
            className="bg-slate-800 border border-slate-700 text-slate-200 text-xs rounded px-2 py-1 focus:ring-1 focus:ring-cyan-500 focus:outline-none"
            aria-label="Filter by Terminal"
          >
            <option value="">All Terminals</option>
            <option value="DCT">Durban Container Terminal (DCT)</option>
            <option value="MPT">Multi-Purpose Terminal (MPT)</option>
            <option value="PIER1">Pier 1 Container Terminal</option>
            <option value="PIER2">Pier 2 Container Terminal</option>
          </select>

          {/* Vessel Type */}
          <select
            value={filters.vesselType}
            onChange={(e) => handleChange('vesselType', e.target.value)}
            className="bg-slate-800 border border-slate-700 text-slate-200 text-xs rounded px-2 py-1 focus:ring-1 focus:ring-cyan-500 focus:outline-none"
            aria-label="Filter by Vessel Type"
          >
            <option value="">All Vessel Types</option>
            <option value="Container">Container</option>
            <option value="Bulker">Bulker</option>
            <option value="Tanker">Tanker</option>
            <option value="General Cargo">General Cargo</option>
            <option value="Passenger (Cruise)">Passenger (Cruise)</option>
          </select>

          {/* Cargo Type */}
          <select
            value={filters.cargoType}
            onChange={(e) => handleChange('cargoType', e.target.value)}
            className="bg-slate-800 border border-slate-700 text-slate-200 text-xs rounded px-2 py-1 focus:ring-1 focus:ring-cyan-500 focus:outline-none"
            aria-label="Filter by Cargo Type"
          >
            <option value="">All Cargo Types</option>
            <option value="Containers">Containers</option>
            <option value="Bulk Minerals">Bulk Minerals</option>
            <option value="Breakbulk">Breakbulk</option>
            <option value="General">General</option>
            <option value="Passengers">Passengers</option>
          </select>

          {/* Data Quality Status */}
          <select
            value={filters.qualityStatus}
            onChange={(e) => handleChange('qualityStatus', e.target.value)}
            className="bg-slate-800 border border-slate-700 text-slate-200 text-xs rounded px-2 py-1 focus:ring-1 focus:ring-cyan-500 focus:outline-none"
            aria-label="Filter by Data Quality Status"
          >
            <option value="">All DQ Statuses</option>
            <option value="CLEAN">Clean [✓]</option>
            <option value="FLAGGED">Flagged [⚠]</option>
            <option value="QUARANTINED">Quarantined [✕]</option>
          </select>
        </div>

        {/* Right: Expand Toggle & Reset */}
        <div className="flex items-center gap-2">
          {activeFilterCount > 0 && (
            <button
              onClick={handleReset}
              className="text-[11px] text-slate-400 hover:text-white underline cursor-pointer"
            >
              Clear ({activeFilterCount})
            </button>
          )}

          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="px-2 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded border border-slate-700 text-xs flex items-center gap-1 cursor-pointer"
          >
            <span>Filters</span>
            {activeFilterCount > 0 && (
              <span className="px-1.5 py-0.2 rounded-full bg-cyan-600 text-white text-[10px] font-bold">
                {activeFilterCount}
              </span>
            )}
            <span className="text-[10px]">{isExpanded ? '▲' : '▼'}</span>
          </button>
        </div>
      </div>

      {/* Expanded Secondary Filters */}
      {isExpanded && (
        <div className="mt-2 pt-2 border-t border-slate-800 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3">
          {/* Date Range Start */}
          <div>
            <label className="block text-[10px] uppercase text-slate-400 font-semibold mb-0.5">
              Start Date
            </label>
            <input
              type="date"
              value={filters.startDate}
              onChange={(e) => handleChange('startDate', e.target.value)}
              className="w-full bg-slate-800 border border-slate-700 text-slate-200 text-xs rounded px-2 py-1 focus:ring-1 focus:ring-cyan-500 focus:outline-none"
            />
          </div>

          {/* Date Range End */}
          <div>
            <label className="block text-[10px] uppercase text-slate-400 font-semibold mb-0.5">
              End Date
            </label>
            <input
              type="date"
              value={filters.endDate}
              onChange={(e) => handleChange('endDate', e.target.value)}
              className="w-full bg-slate-800 border border-slate-700 text-slate-200 text-xs rounded px-2 py-1 focus:ring-1 focus:ring-cyan-500 focus:outline-none"
            />
          </div>

          {/* Berth */}
          <div>
            <label className="block text-[10px] uppercase text-slate-400 font-semibold mb-0.5">
              Berth
            </label>
            <input
              type="text"
              placeholder="e.g. Berth 101"
              value={filters.berth}
              onChange={(e) => handleChange('berth', e.target.value)}
              className="w-full bg-slate-800 border border-slate-700 text-slate-200 text-xs rounded px-2 py-1 focus:ring-1 focus:ring-cyan-500 focus:outline-none"
            />
          </div>

          {/* Movement Type */}
          <div>
            <label className="block text-[10px] uppercase text-slate-400 font-semibold mb-0.5">
              Movement Type
            </label>
            <select
              value={filters.movementType}
              onChange={(e) => handleChange('movementType', e.target.value)}
              className="w-full bg-slate-800 border border-slate-700 text-slate-200 text-xs rounded px-2 py-1 focus:ring-1 focus:ring-cyan-500 focus:outline-none"
            >
              <option value="">All Movements</option>
              <option value="Arrival">Arrival</option>
              <option value="Shifting">Shifting</option>
              <option value="Sailing">Sailing</option>
            </select>
          </div>

          {/* Vessel Size Range */}
          <div>
            <label className="block text-[10px] uppercase text-slate-400 font-semibold mb-0.5">
              Vessel Size (TEU)
            </label>
            <select
              value={filters.vesselSize}
              onChange={(e) => handleChange('vesselSize', e.target.value)}
              className="w-full bg-slate-800 border border-slate-700 text-slate-200 text-xs rounded px-2 py-1 focus:ring-1 focus:ring-cyan-500 focus:outline-none"
            >
              <option value="">All Sizes</option>
              <option value="feeder">Feeder (&lt;3,000 TEU)</option>
              <option value="panamax">Panamax (3,000 - 8,000 TEU)</option>
              <option value="postpanamax">Post-Panamax (&gt;8,000 TEU)</option>
            </select>
          </div>
        </div>
      )}
    </div>
  )
}
