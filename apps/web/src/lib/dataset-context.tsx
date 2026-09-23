'use client'

import React, { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { useAuth } from './auth-context'

export type DatasetState = 'loading' | 'none' | 'processing' | 'ready' | 'failed'

export interface DatasetFileResult {
  filename: string
  checksum?: string
  byte_size: number
  parse_status: string
  validation_status: string
  error_message?: string | null
}

interface ActiveDatasetResponse {
  has_active_dataset: boolean
  batch?: {
    batch_id: string
    file_name: string
    file_checksum: string
    created_at?: string | null
    status: string
    is_active?: boolean
    file_count?: number
    governed_file_count?: number
    skipped_file_count?: number
    files?: DatasetFileResult[]
  } | null
}

interface DatasetContextType {
  status: DatasetState
  batchId?: string
  fileName?: string
  fileChecksum?: string
  errorMessage?: string
  files: DatasetFileResult[]
  refresh: () => Promise<void>
  /** Removes the tenant's active dataset (backend source of truth) and immediately
   * reflects NO_DATASET locally so every page relying on this context updates together. */
  clearDataset: () => Promise<void>
}

const DatasetContext = createContext<DatasetContextType>({
  status: 'loading',
  files: [],
  refresh: async () => {},
  clearDataset: async () => {},
})

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export const DatasetStatusProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { token, isLoading: authLoading } = useAuth()
  const [status, setStatus] = useState<DatasetState>('loading')
  const [batchId, setBatchId] = useState<string | undefined>(undefined)
  const [fileName, setFileName] = useState<string | undefined>(undefined)
  const [fileChecksum, setFileChecksum] = useState<string | undefined>(undefined)
  const [errorMessage, setErrorMessage] = useState<string | undefined>(undefined)
  const [files, setFiles] = useState<DatasetFileResult[]>([])

  const authHeaders = useCallback(() => ({ Authorization: `Bearer ${token || 'dev-token'}` }), [token])

  const refresh = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/ingestion/active`, { headers: authHeaders() })
      if (!res.ok) {
        setStatus('none')
        setBatchId(undefined)
        setFileName(undefined)
        setFileChecksum(undefined)
        setFiles([])
        return
      }
      const data: ActiveDatasetResponse = await res.json()
      if (data.has_active_dataset && data.batch && data.batch.status === 'COMMITTED') {
        setStatus('ready')
        setBatchId(data.batch.batch_id)
        setFileName(data.batch.file_name)
        setFileChecksum(data.batch.file_checksum)
        setFiles(data.batch.files || [])
        setErrorMessage(undefined)
      } else {
        // Check if there are processing or failed batches
        const bRes = await fetch(`${API_BASE}/api/v1/ingestion/batches`, { headers: authHeaders() })
        if (bRes.ok) {
          const batches = await bRes.json()
          if (batches.length > 0 && batches[0].status === 'FAILED') {
            setStatus('failed')
            setErrorMessage(batches[0].error_message || 'The most recent dataset upload failed to process.')
          } else if (batches.length > 0 && batches[0].status === 'PROCESSING') {
            setStatus('processing')
          } else {
            setStatus('none')
          }
        } else {
          setStatus('none')
        }
        setBatchId(undefined)
        setFileName(undefined)
        setFileChecksum(undefined)
        setFiles([])
      }
    } catch {
      setStatus('none')
      setBatchId(undefined)
      setFileName(undefined)
      setFileChecksum(undefined)
      setFiles([])
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
    setBatchId(undefined)
    setFileName(undefined)
    setFileChecksum(undefined)
    setFiles([])
    setErrorMessage(undefined)
  }, [authHeaders])

  useEffect(() => {
    if (authLoading) return
    refresh()
  }, [authLoading, refresh])

  return (
    <DatasetContext.Provider value={{ status, batchId, fileName, fileChecksum, errorMessage, files, refresh, clearDataset }}>
      {children}
    </DatasetContext.Provider>
  )
}

export const useDatasetStatus = () => useContext(DatasetContext)
