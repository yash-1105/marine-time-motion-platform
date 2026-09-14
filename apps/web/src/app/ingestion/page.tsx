'use client'

import { useState } from 'react'
import Link from 'next/link'
import { useAuth } from '@/lib/auth-context'
import { useDatasetStatus } from '@/lib/dataset-context'
import { PageHeader, Card, SectionHeader, StatusBadge, ErrorState } from '@/components/ui'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

type UploadState = 'idle' | 'processing' | 'success' | 'error'

export default function IngestionPage() {
  const { can, token } = useAuth()
  const { refresh: refreshDataset } = useDatasetStatus()
  const [file, setFile] = useState<File | null>(null)
  const [state, setState] = useState<UploadState>('idle')
  const [message, setMessage] = useState<string>('')

  if (!can('create:vessel_call')) {
    return (
      <div className="flex-1 flex items-center justify-center p-8">
        <StatusBadge label="Access Denied — missing create:vessel_call permission" tone="critical" />
      </div>
    )
  }

  const authHeaders = { Authorization: `Bearer ${token || 'dev-token'}` }

  // The ingestion pipeline runs synchronously on the server, so there is no real
  // intermediate progress to poll — show an honest indeterminate state for the
  // single request, then reflect the batch's actual final status.
  const resolveBatchOutcome = async (batchId: string) => {
    const res = await fetch(`${API}/api/v1/ingestion/batches`, { headers: authHeaders })
    if (!res.ok) return null
    const batches: Array<{ batch_id: string; status: string; error_message?: string | null }> = await res.json()
    return batches.find((b) => b.batch_id === batchId) || null
  }

  const handleUpload = async () => {
    if (!file) return
    setState('processing')
    setMessage('')

    const formData = new FormData()
    formData.append('file', file)

    try {
      const res = await fetch(`${API}/api/v1/ingestion/upload`, {
        method: 'POST',
        headers: authHeaders,
        body: formData,
      })
      if (!res.ok) {
        const err = await res.json().catch(() => null)
        throw new Error(err?.detail || `Upload failed (HTTP ${res.status})`)
      }
      const data = await res.json()
      const outcome = await resolveBatchOutcome(data.batch_id)
      if (outcome?.status === 'FAILED') {
        setState('error')
        setMessage(outcome.error_message || 'Dataset processing failed.')
        return
      }
      setState('success')
      setMessage(file.name)
      await refreshDataset()
    } catch (error) {
      const e = error as Error
      setState('error')
      setMessage(e.message)
    }
  }

  const reset = () => {
    setState('idle')
    setMessage('')
    setFile(null)
  }

  return (
    <div className="flex-1 flex flex-col h-full bg-[var(--color-bg)] overflow-y-auto">
      <PageHeader title="Data Ingestion" />

      <div className="p-6 max-w-3xl w-full mx-auto space-y-6">
        {state === 'success' && (
          <Card className="border-[var(--color-good-border)] bg-[var(--color-good-bg)]">
            <div className="flex items-center justify-between gap-4 flex-wrap">
              <div>
                <p className="text-sm font-semibold text-[var(--color-text-primary)]">Dataset processed successfully</p>
                <p className="text-xs text-[var(--color-text-secondary)] mt-0.5">{message}</p>
              </div>
              <div className="flex items-center gap-2">
                <Link
                  href="/"
                  className="px-3.5 py-1.5 bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-white rounded-md text-sm font-medium"
                >
                  View Executive Dashboard
                </Link>
                <button
                  onClick={reset}
                  className="px-3.5 py-1.5 bg-[var(--color-surface)] hover:bg-[var(--color-surface-muted)] text-[var(--color-text-secondary)] rounded-md text-sm font-medium border border-[var(--color-border)] cursor-pointer"
                >
                  Upload another
                </button>
              </div>
            </div>
          </Card>
        )}

        {state === 'error' && (
          <Card>
            <ErrorState title="Dataset processing failed" description={message} onRetry={reset} />
          </Card>
        )}

        {(state === 'idle' || state === 'processing') && (
          <Card>
            <SectionHeader title="Upload vessel operations dataset" description="Supported format: Excel (.xlsx)" />
            <div className="space-y-4">
              <input
                type="file"
                accept=".xlsx"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
                disabled={state === 'processing'}
                className="block w-full text-sm text-[var(--color-text-secondary)] border border-[var(--color-border)] rounded-md p-2 file:mr-3 file:px-3 file:py-1.5 file:rounded-md file:border-0 file:text-xs file:font-medium file:bg-[var(--color-accent-soft)] file:text-[var(--color-accent)] cursor-pointer disabled:opacity-60"
              />
              <button
                onClick={handleUpload}
                disabled={!file || state === 'processing'}
                className="px-4 py-1.5 bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-white rounded-md text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer flex items-center gap-2"
              >
                {state === 'processing' && (
                  <span
                    className="h-3.5 w-3.5 rounded-full border-2 border-white/40 border-t-white animate-spin"
                    aria-hidden="true"
                  />
                )}
                {state === 'processing' ? 'Uploading and processing…' : 'Upload & Process'}
              </button>
            </div>
          </Card>
        )}
      </div>
    </div>
  )
}
