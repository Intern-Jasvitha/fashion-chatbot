import { useState } from 'react'
import { X } from 'lucide-react'

export interface FeedbackModalPayload {
  reasonCode: string
  correctionText: string
  consentLongTerm: boolean
}

interface ChatFeedbackModalProps {
  isOpen: boolean
  onClose: () => void
  onSubmit: (payload: FeedbackModalPayload) => Promise<void> | void
  defaultConsentLongTerm?: boolean
  isSubmitting?: boolean
  title?: string
}

const REASON_OPTIONS = [
  { value: 'INCORRECT', label: 'Incorrect information' },
  { value: 'IRRELEVANT', label: 'Irrelevant response' },
  { value: 'MISSING_DETAIL', label: 'Missing important details' },
  { value: 'STYLE_TONE', label: 'Tone/style mismatch' },
]

export function ChatFeedbackModal({
  isOpen,
  onClose,
  onSubmit,
  defaultConsentLongTerm = false,
  isSubmitting = false,
  title = 'Help us improve this response',
}: ChatFeedbackModalProps) {
  const [reasonCode, setReasonCode] = useState('INCORRECT')
  const [correctionText, setCorrectionText] = useState('')
  const [consentLongTerm, setConsentLongTerm] = useState(defaultConsentLongTerm)

  if (!isOpen) {
    return null
  }

  const handleSubmit = async () => {
    await onSubmit({
      reasonCode,
      correctionText: correctionText.trim(),
      consentLongTerm,
    })
  }

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center px-4">
      <div className="absolute inset-0 bg-black/45" onClick={onClose} aria-hidden="true" />
      <div className="relative w-full max-w-lg rounded-2xl border border-border bg-card p-5 shadow-2xl">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-base font-semibold text-foreground">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1 text-muted-foreground hover:bg-secondary"
            aria-label="Close feedback dialog"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <label className="mb-2 block text-sm font-medium text-foreground">What went wrong?</label>
        <select
          value={reasonCode}
          onChange={(e) => setReasonCode(e.target.value)}
          className="mb-4 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
        >
          {REASON_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>

        <label className="mb-2 block text-sm font-medium text-foreground">Correction (optional)</label>
        <textarea
          value={correctionText}
          onChange={(e) => setCorrectionText(e.target.value)}
          rows={4}
          placeholder="Tell us how the answer should be improved"
          className="mb-4 w-full resize-none rounded-lg border border-border bg-background px-3 py-2 text-sm"
        />

        <label className="mb-4 flex cursor-pointer items-center gap-2 text-sm text-muted-foreground">
          <input
            type="checkbox"
            checked={consentLongTerm}
            onChange={(e) => setConsentLongTerm(e.target.checked)}
            className="h-4 w-4"
          />
          Allow this correction to improve future chats (long-term memory)
        </label>

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-border px-3 py-2 text-sm"
            disabled={isSubmitting}
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            className="rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground disabled:opacity-50"
            disabled={isSubmitting}
          >
            {isSubmitting ? 'Submitting...' : 'Submit feedback'}
          </button>
        </div>
      </div>
    </div>
  )
}
