'use client'

import { useRef, useState } from 'react'
import Link from 'next/link'
import { useAuth } from '@/lib/auth-context'
import { useDatasetStatus } from '@/lib/dataset-context'
import { PageHeader, Card, SectionHeader, StatusBadge, ErrorState, LoadingState } from '@/components/ui'
import { CheckCircle2, FileSpreadsheet, LayoutDashboard, Plus, Trash2, UploadCloud } from 'lucide-react'
import { appendWorkbookSelection, MAX_WORKBOOKS } from './file-selection'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

type UploadState = 'idle' | 'uploading' | 'error'

type FileResult = {
  filename: string
  byte_size: number
  parse_status: string
  validation_status: string
  error_message?: string | null
  message?: string | null
}

type BatchOutcome = {
  batch_id: string
  status: string
  error_message?: string | null
  files?: FileResult[]
}

function FileHandlingSummary({ files, batchStatus }: { files: FileResult[]; batchStatus: string }) {
  if (!files.length) return null
  const skipped = files.filter((file) => file.parse_status === 'SKIPPED').length
  const displayStatus = (file: FileResult) => {
    if (file.parse_status === 'SKIPPED') return { label: 'Skipped — No governed worksheet', tone: 'warning' as const }
    if (file.parse_status === 'FAILED' || file.validation_status === 'FAILED') return { label: 'Failed', tone: 'critical' as const }
    if (batchStatus === 'COMMITTED') return { label: 'Completed', tone: 'good' as const }
    if (file.parse_status === 'QUEUED') return { label: 'Uploading', tone: 'neutral' as const }
    return { label: 'Processing', tone: 'neutral' as const }
  }

  return (
    <div className="mt-5 border-t border-[var(--color-border)] pt-4 text-left">
      <div className="mb-3 flex items-center justify-between gap-3">
        <p className="text-xs font-semibold text-[var(--color-text-primary)]">File handling</p>
        <p className="text-[11px] text-[var(--color-text-tertiary)]">
          {files.length} total · {files.length - skipped} governed / processed · {skipped} skipped
        </p>
      </div>
      <ul className="space-y-2">
        {files.map((file, index) => {
          const state = displayStatus(file)
          const explanation = file.message || file.error_message
          return (
            <li key={`${file.filename}-${index}`} className="flex items-start justify-between gap-4 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface-subtle)] px-3 py-2.5">
              <div className="min-w-0">
                <p className="truncate text-xs font-medium text-[var(--color-text-primary)]" title={file.filename}>{file.filename}</p>
                <p className="mt-0.5 text-[11px] text-[var(--color-text-tertiary)]">
                  {(file.byte_size / 1024 / 1024).toFixed(2)} MB{explanation ? ` · ${explanation}` : ''}
                </p>
              </div>
              <StatusBadge label={state.label} tone={state.tone} />
            </li>
          )
        })}
      </ul>
    </div>
  )
}

export default function IngestionPage() {
  const { can, token, refreshAccessToken, logout } = useAuth()
  const { status: datasetStatus, fileName, files: persistedFiles, refresh: refreshDataset, clearDataset } = useDatasetStatus()
  const [files, setFiles] = useState<File[]>([])
  const [uploadState, setUploadState] = useState<UploadState>('idle')
  const [uploadedName, setUploadedName] = useState<string>('')
  const [errorTitle, setErrorTitle] = useState<string>('Dataset processing failed')
  const [errorMessage, setErrorMessage] = useState<string>('')
  const [fileResults, setFileResults] = useState<FileResult[]>([])
  const [batchStatus, setBatchStatus] = useState<string>('')
  const [confirmingRemoval, setConfirmingRemoval] = useState(false)
  const [removing, setRemoving] = useState(false)
  const addNewInputRef = useRef<HTMLInputElement>(null)
  const selectionInputRef = useRef<HTMLInputElement>(null)

  if (!can('create:vessel_call')) {
    return (
      <div className="flex-1 flex items-center justify-center p-8">
        <StatusBadge label="Access Denied — missing create:vessel_call permission" tone="critical" />
      </div>
    )
  }

  const getActiveAuthHeaders = (): Record<string, string> => {
    let currentToken = token
    if (!currentToken && typeof window !== 'undefined') {
      currentToken = localStorage.getItem('auth_token') || undefined
    }
    return { Authorization: `Bearer ${currentToken || 'dev-token'}` }
  }

  const resolveBatchOutcome = async (batchId: string) => {
    const res = await fetch(`${API}/api/v1/ingestion/batches`, { headers: getActiveAuthHeaders() })
    if (!res.ok) return null
    const batches: BatchOutcome[] = await res.json()
    return batches.find((b) => b.batch_id === batchId) || null
  }

  const waitForBatchOutcome = async (batchId: string) => {
    // Processing happens on the durable worker so the upload request is not held
    // open across a browser/proxy timeout.  Keep the user informed until the
    // persisted batch reaches a terminal state.
    let consecutiveNetworkFailures = 0
    for (let attempt = 0; attempt < 300; attempt += 1) {
      let outcome: BatchOutcome | null = null
      try {
        outcome = await resolveBatchOutcome(batchId)
        consecutiveNetworkFailures = 0
      } catch (error) {
        if (!(error instanceof TypeError) || !/fetch|network/i.test(error.message)) throw error
        consecutiveNetworkFailures += 1
        if (consecutiveNetworkFailures >= 5) {
          throw new Error(
            'The upload was accepted, but its processing status is temporarily unavailable. Refresh this page to resume from the persisted batch state.'
          )
        }
      }
      if (outcome) {
        setBatchStatus(outcome.status)
        if (outcome.files) setFileResults(outcome.files)
      }
      if (outcome?.status === 'COMMITTED' || outcome?.status === 'FAILED' || outcome?.status === 'SUPERSEDED') return outcome
      await new Promise((resolve) => window.setTimeout(resolve, 2000))
    }
    throw new Error('Upload was accepted but processing is still running. Refresh this page to check its persisted batch status.')
  }

  const processUpload = async (targetFiles: File[]) => {
    setUploadState('uploading')
    setErrorTitle('Dataset processing failed')
    setErrorMessage('')
    setBatchStatus('UPLOADING')
    setFileResults(targetFiles.map((targetFile) => ({
      filename: targetFile.name,
      byte_size: targetFile.size,
      parse_status: 'QUEUED',
      validation_status: 'PENDING',
    })))

    const uploadBody = () => {
      const formData = new FormData()
      targetFiles.forEach((targetFile) => formData.append('files', targetFile, targetFile.name))
      return formData
    }

    let uploadAccepted = false
    try {
      let headers = getActiveAuthHeaders()
      let res = await fetch(`${API}/api/v1/ingestion/upload`, {
        method: 'POST',
        headers,
        body: uploadBody(),
      })

      // If unauthorized, attempt to refresh access token once and retry
      if (res.status === 401) {
        const freshToken = await refreshAccessToken()
        if (freshToken) {
          headers = { Authorization: `Bearer ${freshToken}` }
          res = await fetch(`${API}/api/v1/ingestion/upload`, {
            method: 'POST',
            headers,
            body: uploadBody(),
          })
        }
      }

      if (!res.ok) {
        const err = await res.json().catch(() => null)
        const parsedMessage =
          err?.message ||
          err?.detail?.message ||
          (typeof err?.detail === 'string' ? err.detail : null) ||
          (res.status === 401
            ? 'Session expired. Please sign in again.'
            : `Upload failed (HTTP ${res.status})`)

        if (res.status === 401) {
          await logout()
        }
        throw new Error(parsedMessage)
      }
      const data = await res.json()
      if (data.file_count !== targetFiles.length) {
        throw new Error(
          `Upload integrity check failed: ${targetFiles.length} workbooks were selected but the server received ${data.file_count ?? 0}.`
        )
      }
      uploadAccepted = true
      if (Array.isArray(data.file_results)) setFileResults(data.file_results)
      setBatchStatus(data.status)
      const outcome = await waitForBatchOutcome(data.batch_id)
      if (outcome?.status === 'FAILED' || outcome?.status === 'SUPERSEDED') {
        setUploadState('error')
        setErrorTitle(outcome.status === 'SUPERSEDED' ? 'Dataset upload superseded' : 'Dataset processing failed')
        setErrorMessage(outcome.error_message || (outcome.status === 'SUPERSEDED'
          ? 'This upload was superseded by a newer dataset upload. Refresh to view its persisted status.'
          : 'Dataset processing failed.'))
        return
      }
      setUploadedName(targetFiles.length === 1 ? targetFiles[0].name : `${targetFiles.length} workbooks`)
      setFiles([])
      setUploadState('idle')
      await refreshDataset()
    } catch (error) {
      const e = error as Error
      setUploadState('error')
      setErrorTitle(uploadAccepted ? 'Processing status unavailable' : 'Dataset upload failed')
      setErrorMessage(
        e instanceof TypeError && /fetch|network/i.test(e.message)
          ? 'Could not reach the ingestion service. Check your connection and retry; the active dataset was not changed.'
          : e.message
      )
    }
  }

  const addToSelection = (incoming: File[]) => {
    const excelFiles = incoming.filter((candidate) => candidate.name.toLowerCase().endsWith('.xlsx'))
    const ignoredTypeCount = incoming.length - excelFiles.length
    const result = appendWorkbookSelection(files, excelFiles)
    setFiles(result.files)
    const messages: string[] = []
    if (ignoredTypeCount) messages.push(`${ignoredTypeCount} non-XLSX file${ignoredTypeCount === 1 ? ' was' : 's were'} ignored.`)
    if (result.duplicateCount) messages.push(`${result.duplicateCount} duplicate selection${result.duplicateCount === 1 ? ' was' : 's were'} ignored.`)
    if (result.rejectedForLimit) messages.push(`A maximum of ${MAX_WORKBOOKS} workbooks is allowed. File #16 was not added.`)
    setErrorMessage(messages.join(' '))
  }

  const handleInitialUpload = async () => {
    if (!files.length) return
    await processUpload(files)
  }

  const handleAddNewFileSelected = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = Array.from(e.target.files || [])
    if (!selected.length) return
    // Reset the input value so the same file can be re-selected if needed
    e.target.value = ''
    if (selected.length > 15) {
      setErrorMessage('A dataset group supports a maximum of 15 workbooks. File #16 was not added.')
      setUploadState('error')
      return
    }
    await processUpload(selected)
  }

  const retry = () => {
    setUploadState('idle')
    setErrorTitle('Dataset processing failed')
    setErrorMessage('')
    setFileResults([])
    setBatchStatus('')
  }

  const handleConfirmRemove = async () => {
    setRemoving(true)
    try {
      await clearDataset()
      setUploadedName('')
      setFiles([])
    } catch {
      // Handled via context
    } finally {
      setRemoving(false)
      setConfirmingRemoval(false)
    }
  }

  const displayFileName = uploadedName || fileName || 'Vessel Operations Dataset'

  return (
    <div className="flex-1 flex flex-col h-full bg-[var(--color-bg)] overflow-y-auto">
      <PageHeader title="Data Ingestion" />

      {/* Hidden file input for "Add New" action */}
      <input
        type="file"
        ref={addNewInputRef}
        accept=".xlsx"
        multiple
        onChange={handleAddNewFileSelected}
        className="hidden"
        aria-hidden="true"
      />

      <div className="flex-1 flex items-start justify-center p-6 lg:p-8">
      <div className="max-w-3xl w-full space-y-6">
        {uploadState === 'uploading' ? (
          <Card>
            <LoadingState label="Uploading and processing dataset…" />
            <FileHandlingSummary files={fileResults} batchStatus={batchStatus} />
          </Card>
        ) : uploadState === 'error' ? (
          <Card>
            <ErrorState title={errorTitle} description={errorMessage} onRetry={retry} />
            <FileHandlingSummary files={fileResults} batchStatus={batchStatus} />
          </Card>
        ) : datasetStatus === 'loading' ? (
          <Card>
            <LoadingState label="Checking dataset status…" />
          </Card>
        ) : datasetStatus === 'ready' ? (
          <Card className="overflow-hidden border-[var(--color-good-border)]">
            <div className="flex items-start justify-between gap-5 flex-wrap">
              <div className="flex items-center gap-4 min-w-0">
                <div className="flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-[var(--radius-lg)] border border-[var(--color-good-border)] bg-[var(--color-good-bg)] text-[var(--color-good)]">
                  <FileSpreadsheet size={23} strokeWidth={1.7} aria-hidden="true" />
                </div>
                <div className="min-w-0">
                  <div className="mb-1 flex items-center gap-2">
                    <p className="text-sm font-semibold text-[var(--color-text-primary)]">Active dataset</p>
                    <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-[var(--color-good)]"><CheckCircle2 size={12} /> Ready</span>
                  </div>
                  <p className="truncate text-xs text-[var(--color-text-secondary)]" title={displayFileName}>{displayFileName}</p>
                  <p className="mt-1 text-[11px] text-[var(--color-text-tertiary)]">Available to all governed analytics experiences</p>
                </div>
              </div>
              <div className="flex items-center gap-2 flex-wrap">
                <button
                  onClick={() => addNewInputRef.current?.click()}
                  className="inline-flex min-h-9 items-center gap-1.5 px-3.5 py-2 bg-[var(--color-surface)] hover:bg-[var(--color-surface-muted)] text-[var(--color-text-primary)] rounded-[var(--radius-md)] text-xs font-semibold border border-[var(--color-border-strong)] cursor-pointer"
                  title="Select one to fifteen Excel workbooks to replace the active dataset"
                >
                  <Plus size={14} aria-hidden="true" /> Add New
                </button>
                <Link
                  href="/"
                  className="inline-flex min-h-9 items-center gap-1.5 px-3.5 py-2 bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-white rounded-[var(--radius-md)] text-xs font-semibold shadow-sm"
                >
                  <LayoutDashboard size={14} aria-hidden="true" /> View Dashboard
                </Link>
                <button
                  onClick={() => setConfirmingRemoval(true)}
                  className="inline-flex min-h-9 items-center gap-1.5 px-3.5 py-2 bg-[var(--color-surface)] hover:bg-[var(--color-critical-bg)] hover:text-[var(--color-critical)] text-[var(--color-text-secondary)] rounded-[var(--radius-md)] text-xs font-semibold border border-[var(--color-border-strong)] cursor-pointer"
                >
                  <Trash2 size={14} aria-hidden="true" /> Remove
                </button>
              </div>
            </div>
            <FileHandlingSummary files={fileResults.length ? fileResults : persistedFiles} batchStatus={batchStatus || 'COMMITTED'} />
          </Card>
        ) : (
          <div className="space-y-4">
            <div
              onDragOver={(event) => event.preventDefault()}
              onDrop={(event) => {
                event.preventDefault()
                addToSelection(Array.from(event.dataTransfer.files))
              }}
            >
            <Card className="text-center">
              <div className="mx-auto mb-5 flex h-14 w-14 items-center justify-center rounded-[14px] border border-[var(--color-accent-soft-border)] bg-[var(--color-accent-soft)] text-[var(--color-accent)]">
                <UploadCloud size={26} strokeWidth={1.6} aria-hidden="true" />
              </div>
              <SectionHeader className="justify-center" title="Upload vessel operations dataset" description="Drop one to fifteen governed Excel workbooks here, or select them below, for one atomic dataset ingestion." />
              <div className="mx-auto mt-6 max-w-xl space-y-4 text-left">
                <input
                  ref={selectionInputRef}
                  type="file"
                  accept=".xlsx"
                  multiple
                  onChange={(e) => {
                    const selected = Array.from(e.target.files || [])
                    e.target.value = ''
                    addToSelection(selected)
                  }}
                  className="sr-only"
                  aria-label="Select Excel workbooks"
                />
                <button
                  type="button"
                  onClick={() => selectionInputRef.current?.click()}
                  disabled={files.length >= MAX_WORKBOOKS}
                  className="inline-flex min-h-10 w-full items-center justify-center gap-2 rounded-[var(--radius-lg)] border border-dashed border-[var(--color-border-strong)] bg-[var(--color-surface-subtle)] px-4 py-3 text-xs font-semibold text-[var(--color-accent-strong)] hover:border-[var(--color-accent-soft-border)] hover:bg-[var(--color-accent-soft)] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <Plus size={15} aria-hidden="true" />
                  {files.length ? 'Add more workbooks' : 'Choose workbooks'}
                </button>
                {errorMessage && (
                  <p role="status" className="text-xs text-[var(--color-warning)]">{errorMessage}</p>
                )}
                <button
                  onClick={handleInitialUpload}
                  disabled={!files.length}
                  className="inline-flex min-h-10 w-full items-center justify-center gap-2 px-4 py-2 bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-white rounded-[var(--radius-md)] text-sm font-semibold disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer shadow-sm"
                >
                  <UploadCloud size={16} aria-hidden="true" /> Upload {files.length || ''} {files.length === 1 ? 'workbook' : 'workbooks'} &amp; Process
                </button>
                <p className="text-center text-[11px] text-[var(--color-text-tertiary)]">Files selected: {files.length} / {MAX_WORKBOOKS} · Excel (.xlsx) · validated, lineage-tracked, and processed as one dataset group</p>
                {files.length > 0 && <ul className="space-y-1 text-xs text-[var(--color-text-secondary)]">{files.map((selected, index) => <li key={`${selected.name}-${selected.size}-${selected.lastModified}`} className="flex items-center justify-between gap-3 rounded border border-[var(--color-border)] px-2 py-1.5"><span className="min-w-0 truncate" title={selected.name}>{selected.name} · {(selected.size / 1024 / 1024).toFixed(2)} MB</span><button type="button" aria-label={`Remove ${selected.name}`} onClick={() => setFiles((current) => current.filter((_, i) => i !== index))} className="shrink-0 text-[var(--color-critical)] cursor-pointer">Remove</button></li>)}</ul>}
              </div>
            </Card>
            </div>
          </div>
        )}
      </div>
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
