export const MAX_WORKBOOKS = 15

export type FileSelectionResult = {
  files: File[]
  duplicateCount: number
  rejectedForLimit: boolean
}

const identity = (file: File) => `${file.name}\u0000${file.size}\u0000${file.lastModified}`

/** Append browser selections deterministically while preserving the visible order. */
export function appendWorkbookSelection(current: File[], incoming: File[]): FileSelectionResult {
  const selected = [...current]
  const identities = new Set(selected.map(identity))
  let duplicateCount = 0
  let rejectedForLimit = false

  for (const file of incoming) {
    const key = identity(file)
    if (identities.has(key)) {
      duplicateCount += 1
      continue
    }
    if (selected.length >= MAX_WORKBOOKS) {
      rejectedForLimit = true
      continue
    }
    selected.push(file)
    identities.add(key)
  }

  return { files: selected, duplicateCount, rejectedForLimit }
}

