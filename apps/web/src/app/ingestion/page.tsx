'use client'

import { useState } from 'react'
import Link from 'next/link'
import { useAuth } from '@/lib/auth-context'
import { useDatasetStatus } from '@/lib/dataset-context'
import { PageHeader, Card, SectionHeader, StatusBadge, ErrorState, LoadingState } from '@/components/ui'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

type UploadState = 'idle' | 'uploading' | 'error'

export default function IngestionPage() {
  const { can, token } = useAuth()
  const { status: datasetStatus, refresh: refreshDataset, clearDataset } = useDatasetStatus()
  const [file, setFile] = useState<File | null>(null)
  const [uploadState, setUploadState] = useState<UploadState>('idle')
  const [uploadedName, setUploadedName] = useState<string>('')
  const [errorMessage, setErrorMessage] = useState<string>('')
  const [confirmingRemoval, setConfirmingRemoval] = useState(false)
  const [removing, setRemoving] = useState(false)

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
    setUploadState('uploading')
    setErrorMessage('')

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
        setUploadState('error')
        setErrorMessage(outcome.error_message || 'Dataset processing failed.')
        return
      }
      setUploadedName(file.name)
      setFile(null)
      setUploadState('idle')
      await refreshDataset()
    } catch (error) {
      const e = error as Error
      setUploadState('error')
      setErrorMessage(e.message)
    }
  }

  const retry = () => {
    setUploadState('idle')
    setErrorMessage('')
  }

  const handleConfirmRemove = async () => {
    setRemoving(true)
    try {
      await clearDataset()
      setUploadedName('')
      setFile(null)
    } catch {
      // Dataset context already reflects failure via its own state if the call fails;
      // keep the confirmation dialog open-free and let the user retry the action.
    } finally {
      setRemoving(false)
      setConfirmingRemoval(false)
    }
  }

  return (
    <div className="flex-1 flex flex-col h-full bg-[var(--color-bg)] overflow-y-auto">
      <PageHeader title="Data Ingestion" />

      <div className="p-6 max-w-3xl w-full mx-auto space-y-6">
        {uploadState === 'uploading' ? (
          <Card>
            <LoadingState label="Uploading and processing dataset…" />
          </Card>
        ) : uploadState === 'error' ? (
          <Card>
            <ErrorState title="Dataset processing failed" description={errorMessage} onRetry={retry} />
          </Card>
        ) : datasetStatus === 'loading' ? (
          <Card>
            <LoadingState label="Checking dataset status…" />
          </Card>
        ) : datasetStatus === 'ready' ? (
          <Card className="border-[var(--color-good-border)] bg-[var(--color-good-bg)]">
            <div className="flex items-center justify-between gap-4 flex-wrap">
              <div>
                <p className="text-sm font-semibold text-[var(--color-text-primary)]">Dataset loaded</p>
                {uploadedName && <p className="text-xs text-[var(--color-text-secondary)] mt-0.5">{uploadedName}</p>}
              </div>
              <div className="flex items-center gap-2">
                <Link
                  href="/"
                  className="px-3.5 py-1.5 bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-white rounded-md text-sm font-medium"
                >
                  View Executive Dashboard
                </Link>
                <button
                  onClick={() => setConfirmingRemoval(true)}
                  className="px-3.5 py-1.5 bg-[var(--color-surface)] hover:bg-[var(--color-critical-bg)] hover:text-[var(--color-critical)] text-[var(--color-text-secondary)] rounded-md text-sm font-medium border border-[var(--color-border)] cursor-pointer"
                >
                  Remove Dataset
                </button>
              </div>
            </div>
          </Card>
        ) : (
          <Card>
            <SectionHeader title="Upload vessel operations dataset" description="Supported format: Excel (.xlsx)" />
            <div className="space-y-4">
              <input
                type="file"
                accept=".xlsx"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
                className="block w-full text-sm text-[var(--color-text-secondary)] border border-[var(--color-border)] rounded-md p-2 file:mr-3 file:px-3 file:py-1.5 file:rounded-md file:border-0 file:text-xs file:font-medium file:bg-[var(--color-accent-soft)] file:text-[var(--color-accent)] cursor-pointer"
              />
              <button
                onClick={handleUpload}
                disabled={!file}
                className="px-4 py-1.5 bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-white rounded-md text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
              >
                Upload &amp; Process
              </button>
            </div>
          </Card>
        )}
      </div>

      {confirmingRemoval && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 backdrop-blur-sm p-4"
          role="dialog"
          aria-modal="true"
        >
          <div className="bg-[var(--color-surface)] rounded-lg shadow-xl max-w-sm w-full border border-[var(--color-border)] p-5 space-y-4">
            <div>
              <p className="text-sm font-semibold text-[var(--color-text-primary)]">Remove current dataset?</p>
              <p className="text-xs text-[var(--color-text-secondary)] mt-1">
                This will clear the active dataset and return you to the upload screen.
              </p>
            </div>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setConfirmingRemoval(false)}
                disabled={removing}
                className="px-3.5 py-1.5 border border-[var(--color-border)] text-[var(--color-text-primary)] rounded-md text-sm font-medium hover:bg-[var(--color-surface-muted)] cursor-pointer disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirmRemove}
                disabled={removing}
                className="px-3.5 py-1.5 bg-[var(--color-critical)] hover:opacity-90 text-white rounded-md text-sm font-medium cursor-pointer disabled:opacity-50"
              >
                {removing ? 'Removing…' : 'Remove Dataset'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
