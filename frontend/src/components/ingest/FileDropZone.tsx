import { useCallback, useRef, useState } from 'react'
import { X } from 'lucide-react'

import { cn } from '@/lib/utils'
import { ACCEPTED_EXTENSIONS } from '@/lib/api-types'

/** 50MB, matching the limit stated in the zone's helper text. */
export const MAX_FILE_BYTES = 50 * 1024 * 1024

export interface FileDropZoneProps {
  files: File[]
  onFilesChange: (files: File[]) => void
  /** Rejected-file message, owned by the parent so it sits with other errors. */
  onRejected: (message: string | null) => void
  disabled?: boolean
  className?: string
}

function extensionOf(name: string): string {
  const dot = name.lastIndexOf('.')
  return dot === -1 ? '' : name.slice(dot).toLowerCase()
}

/**
 * Document-upload mark for the drop zone: a sheet with a folded corner and an
 * arrow rising out of it.
 *
 * Hand-drawn rather than a lucide icon because it is two-tone — the sheet is
 * drawn in the muted text colour so it reads as an outline, and only the arrow
 * carries the accent, which is what makes the "upload" part of it read at this
 * size. A single-colour icon at 56px either shouts or disappears.
 *
 * Deliberately no filled circle behind it: the drop zone is already a bounded
 * region, and a second container inside it just adds a shape to explain.
 */
function DocumentUploadMark() {
  return (
    <svg
      aria-hidden
      width="56"
      height="56"
      viewBox="0 0 24 24"
      fill="none"
      strokeWidth="1.25"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <g className="stroke-text-muted">
        <path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z" />
        <path d="M14 2v4a2 2 0 0 0 2 2h4" />
      </g>
      <g className="stroke-accent">
        <path d="M12 18v-6" />
        <path d="m9 15 3-3 3 3" />
      </g>
    </svg>
  )
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

/**
 * Drop target and file picker for the ingest screen.
 *
 * Validation happens here rather than at submit: the pipeline only reads PDF
 * and CSV (backend/pipeline/types.py::InputType), and a 60MB file or an .xlsx
 * would otherwise travel all the way to the server to come back as a 400. The
 * rejection names the file and the reason.
 */
export function FileDropZone({
  files,
  onFilesChange,
  onRejected,
  disabled = false,
  className,
}: FileDropZoneProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)

  const accept = (incoming: FileList | null) => {
    if (!incoming || incoming.length === 0) return

    const kept: File[] = []
    const rejected: string[] = []

    for (const file of Array.from(incoming)) {
      const ext = extensionOf(file.name)
      if (!ACCEPTED_EXTENSIONS.includes(ext as (typeof ACCEPTED_EXTENSIONS)[number])) {
        rejected.push(`${file.name} — ${ext || 'no extension'} is not supported`)
      } else if (file.size > MAX_FILE_BYTES) {
        rejected.push(`${file.name} — ${formatSize(file.size)} exceeds the 50MB limit`)
      } else {
        kept.push(file)
      }
    }

    onRejected(rejected.length ? rejected.join('; ') : null)
    if (kept.length) onFilesChange([...files, ...kept])
  }

  const browse = useCallback(() => {
    if (!disabled) inputRef.current?.click()
  }, [disabled])

  return (
    <div className={className}>
      <div
        // A button would nest the SELECT FILES button inside it, which is
        // invalid; a div with an explicit role and key handler keeps the whole
        // zone clickable without that.
        role="button"
        tabIndex={disabled ? -1 : 0}
        aria-disabled={disabled || undefined}
        aria-label="Drop files here or click to browse"
        onClick={browse}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            browse()
          }
        }}
        onDragOver={(e) => {
          e.preventDefault()
          if (!disabled) setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDragging(false)
          if (!disabled) accept(e.dataTransfer.files)
        }}
        className={cn(
          'flex cursor-pointer flex-col items-center justify-center gap-4 border border-dashed px-6 py-12 text-center transition-colors',
          dragging
            ? 'border-accent bg-accent/5'
            : 'border-border hover:border-text-muted',
          disabled && 'cursor-not-allowed opacity-50',
        )}
      >
        <DocumentUploadMark />

        <div className="flex flex-col gap-1.5">
          <h3 className="font-mono text-lg tracking-[0.04em] text-text-primary">
            DROP PDF / CSV / OR PASTE URL
          </h3>
          <p className="font-mono text-2xs text-text-muted">
            or click to browse files
          </p>
        </div>

        <button
          type="button"
          disabled={disabled}
          onClick={(e) => {
            // The zone itself already opens the picker; without this the click
            // would bubble and open it twice.
            e.stopPropagation()
            browse()
          }}
          className="border border-accent px-4 py-2 font-sans text-2xs uppercase tracking-[0.14em] text-accent transition-colors hover:bg-accent/10 disabled:opacity-50"
        >
          Select Files
        </button>

        {/* Copy per the approved design. Note this names XLSX, which stage 1
            cannot read (pipeline/types.py::InputType is pdf|csv|text|url) — an
            .xlsx picked here is rejected by the validation above with a
            specific message rather than failing at the server. */}
        <p className="font-mono text-3xs text-text-muted">
          Supported formats: PDF, CSV, XLSX &nbsp;|&nbsp; Max file size: 50MB
        </p>

        <input
          ref={inputRef}
          type="file"
          multiple
          accept={ACCEPTED_EXTENSIONS.join(',')}
          className="hidden"
          onChange={(e) => {
            accept(e.target.files)
            // Reset so picking the same file twice still fires onChange.
            e.target.value = ''
          }}
        />
      </div>

      {files.length > 0 && (
        <ul className="mt-3 flex flex-col gap-2">
          {files.map((file, i) => (
            <li
              key={`${file.name}-${i}`}
              className="flex items-center gap-3 border border-border bg-surface px-3 py-2"
            >
              <span className="min-w-0 flex-1 truncate font-mono text-2xs text-text-primary">
                {file.name}
              </span>
              <span className="shrink-0 font-mono text-3xs text-text-muted">
                {formatSize(file.size)}
              </span>
              <button
                type="button"
                aria-label={`Remove ${file.name}`}
                onClick={() => onFilesChange(files.filter((_, j) => j !== i))}
                className="shrink-0 text-text-muted transition-colors hover:text-text-primary"
              >
                <X size={12} strokeWidth={1.75} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
