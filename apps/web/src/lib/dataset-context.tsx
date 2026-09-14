'use client'

import React, { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { useAuth } from './auth-context'

export type DatasetState = 'loading' | 'none' | 'processing' | 'ready' | 'failed'

interface DatasetContextType {
  status: DatasetState
  errorMessage?: string
  refresh: () => Promise<void>
  /** Removes the tenant's active dataset (backend source of truth) and immediately
   * reflects NO_DATASET locally so every page relying on this context updates together. */
  clearDataset: () => Promise<void>
}

const DatasetContext = createContext<DatasetContextType>({
  status: 'loading',
  refresh: async () => {},
  clearDataset: async () => {},
})

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface BatchRecord {
  batch_id: string
  file_name: string
  status: string
  error_message?: string | null
}

/**
 * Reuses the existing ingestion batch record (the backend's own source of truth for
 * ingestion state) to determine whether real analytical data is available, instead of
 * a frontend-only guess. The most recent batch for the tenant determines the state:
 *
 *   NO_DATASET ('none') -> PROCESSING ('processing') -> DATASET_READY ('ready')
 *   DATASET_READY -> (clearDataset) -> NO_DATASET
 *
 * There is no localStorage/sessionStorage flag to keep in sync — every consumer reads
 * this same context, so a refresh or a clearDataset() call updates every analytics page
 * at once, and a browser refresh re-derives state from the backend rather than replaying
 * a stale client-side flag.
 */
export const DatasetStatusProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { token, isLoading: authLoading } = useAuth()
  const [status, setStatus] = useState<DatasetState>('loading')
  const [errorMessage, setErrorMessage] = useState<string | undefined>(undefined)

  const authHeaders = useCallback(() => ({ Authorization: `Bearer ${token || 'dev-token'}` }), [token])

  const refresh = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/ingestion/batches`, { headers: authHeaders() })
      if (!res.ok) {
        setStatus('none')
        return
      }
      const batches: BatchRecord[] = await res.json()
      if (!batches.length) {
        setStatus('none')
        setErrorMessage(undefined)
        return
      }
      const latest = batches[0]
      if (latest.status === 'COMMITTED') {
        setStatus('ready')
        setErrorMessage(undefined)
      } else if (latest.status === 'FAILED') {
        setStatus('failed')
        setErrorMessage(latest.error_message || 'The most recent dataset upload failed to process.')
      } else {
        setStatus('processing')
      }
    } catch {
      setStatus('none')
    }
  }, [authHeaders])

  const clearDataset = useCallback(async () => {
    const res = await fetch(`${API_BASE}/api/v1/ingestion/dataset`, {
      method: 'DELETE',
      headers: authHeaders(),
    })
    if (!res.ok) {
      throw new Error(`Failed to clear dataset (HTTP ${res.status})`)
    }
    // Reflect NO_DATASET immediately rather than waiting on a re-fetch — every page
    // reading this context re-renders to the empty state right away.
    setStatus('none')
    setErrorMessage(undefined)
  }, [authHeaders])

  useEffect(() => {
    if (authLoading) return
    refresh()
  }, [authLoading, refresh])

  return (
    <DatasetContext.Provider value={{ status, errorMessage, refresh, clearDataset }}>
      {children}
    </DatasetContext.Provider>
  )
}

export const useDatasetStatus = () => useContext(DatasetContext)
