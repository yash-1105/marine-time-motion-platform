'use client'

import React, { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { useAuth } from './auth-context'

export type DatasetState = 'loading' | 'none' | 'processing' | 'ready' | 'failed'

interface DatasetContextType {
  status: DatasetState
  errorMessage?: string
  refresh: () => Promise<void>
}

const DatasetContext = createContext<DatasetContextType>({
  status: 'loading',
  refresh: async () => {},
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
 * a frontend-only guess. The most recent batch for the tenant determines the state.
 */
export const DatasetStatusProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { token, isLoading: authLoading } = useAuth()
  const [status, setStatus] = useState<DatasetState>('loading')
  const [errorMessage, setErrorMessage] = useState<string | undefined>(undefined)

  const refresh = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/ingestion/batches`, {
        headers: { Authorization: `Bearer ${token || 'dev-token'}` },
      })
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
  }, [token])

  useEffect(() => {
    if (authLoading) return
    refresh()
  }, [authLoading, refresh])

  return <DatasetContext.Provider value={{ status, errorMessage, refresh }}>{children}</DatasetContext.Provider>
}

export const useDatasetStatus = () => useContext(DatasetContext)
