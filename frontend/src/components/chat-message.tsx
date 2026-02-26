import { User, ThumbsUp, ThumbsDown, Copy } from 'lucide-react'
import { memo, useCallback, useMemo, useState } from 'react'

/* js-hoist-regexp: Hoist RegExp outside component to avoid recreation on every render */
const BULLET_REGEX = /^[•*-]\s+(.+)$/
const NUMBERED_REGEX = /^\d+\.\s+(.+)$/
const BOLD_REPLACE_REGEX = /\*\*(.+?)\*\*/g
const BOLD_SEGMENT_REGEX = /(\*\*[^*]+\*\*)/g
const BOLD_TOKEN_REGEX = /^\*\*[^*]+\*\*$/

interface ChatMessageProps {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
  backendMessageId?: string
  feedbackType?: 'UP' | 'DOWN' | null
  onFeedback?: (messageId: string, feedbackType: 'UP' | 'DOWN') => void | Promise<void>
  onRequireSignIn?: () => void
  isGuest?: boolean
  isConsecutive?: boolean
  isLastInGroup?: boolean
}

function formatContent(text: string) {
  const parts: Array<{ type: 'text' | 'list'; content: string }> = []
  const lines = text.split('\n')
  let currentList: string[] = []
  let currentText = ''

  const flushList = () => {
    if (currentList.length) {
      parts.push({ type: 'list', content: currentList.join('\n') })
      currentList = []
    }
  }

  const flushText = () => {
    if (currentText.trim()) {
      parts.push({ type: 'text', content: currentText.trim() })
      currentText = ''
    }
  }

  for (const line of lines) {
    const bulletMatch = line.match(BULLET_REGEX) || line.match(NUMBERED_REGEX)
    if (bulletMatch) {
      flushText()
      currentList.push(bulletMatch[1].replace(BOLD_REPLACE_REGEX, '$1'))
    } else {
      flushList()
      currentText += (currentText ? '\n\n' : '') + line
    }
  }
  flushList()
  flushText()
  return parts
}

function renderTextWithBold(text: string) {
  const segments = text.split(BOLD_SEGMENT_REGEX)
  return segments.map((seg, i) =>
    BOLD_TOKEN_REGEX.test(seg) ? (
      <strong key={i} className="font-semibold">{seg.slice(2, -2)}</strong>
    ) : (
      seg
    )
  )
}

export const ChatMessage = memo(function ChatMessage({
  role,
  content,
  timestamp,
  backendMessageId,
  feedbackType,
  onFeedback,
  onRequireSignIn,
  isGuest = false,
  isConsecutive = false,
  isLastInGroup = true,
}: ChatMessageProps) {
  const isUser = role === 'user'
  const parts = useMemo(() => formatContent(content), [content])
  const timestampLabel = useMemo(
    () => timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    [timestamp]
  )
  const [copied, setCopied] = useState(false)

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(content)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }, [content])

  const handleFeedback = useCallback(
    (nextType: 'UP' | 'DOWN') => {
      if (isGuest) {
        onRequireSignIn?.()
        return
      }
      if (!backendMessageId || !onFeedback) return
      onFeedback(backendMessageId, nextType)
    },
    [backendMessageId, isGuest, onFeedback, onRequireSignIn]
  )

  const avatar = (
    <div className="flex-shrink-0 w-8 h-8 sm:w-9 sm:h-9 rounded-full flex items-center justify-center bg-foreground/10 text-foreground">
      {isUser ? (
        <User className="w-4 h-4" strokeWidth={1.5} />
      ) : (
        <span className="text-[10px] sm:text-xs font-semibold">AI</span>
      )}
    </div>
  )

  const bubble = (
    <div
      className={`rounded-2xl px-4 py-3 max-w-[85%] sm:max-w-[28rem] transition-colors duration-200 ${
        isConsecutive ? 'mt-1' : 'mt-4'
      } ${!isLastInGroup ? 'rounded-b-md' : ''}`}
      title={timestampLabel}
      style={{
        backgroundColor: isUser ? 'var(--msg-user-bg)' : 'var(--msg-assistant-bg)',
        borderWidth: '1px',
        borderColor: isUser ? 'var(--msg-user-border)' : 'var(--msg-assistant-border)',
      }}
    >
      <div className="text-sm leading-relaxed text-foreground font-light space-y-2">
        {parts.map((part, i) =>
          part.type === 'text' ? (
            <p key={i} className="whitespace-pre-wrap">
              {renderTextWithBold(part.content)}
            </p>
          ) : (
            <ul key={i} className="space-y-1 pl-0 list-none">
              {part.content.split('\n').map((item, j) => (
                <li key={j} className="flex gap-2">
                  <span className="flex-shrink-0 w-1 h-1 rounded-full bg-foreground/50 mt-1.5" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          )
        )}
      </div>
      {!isUser && isLastInGroup && (
        <div className="flex items-center gap-1 mt-2 pt-2 border-t border-border/50">
          <button
            type="button"
            onClick={() => handleFeedback('UP')}
            className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-foreground/10 transition-colors"
            aria-label="Good response"
            title={isGuest ? 'Sign in to submit feedback' : 'Good response'}
          >
            <ThumbsUp className={`w-3.5 h-3.5 ${feedbackType === 'UP' ? 'text-green-600' : ''}`} />
          </button>
          <button
            type="button"
            onClick={() => handleFeedback('DOWN')}
            className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-foreground/10 transition-colors"
            aria-label="Bad response"
            title={isGuest ? 'Sign in to submit feedback' : 'Bad response'}
          >
            <ThumbsDown className={`w-3.5 h-3.5 ${feedbackType === 'DOWN' ? 'text-red-600' : ''}`} />
          </button>
          <button
            type="button"
            onClick={handleCopy}
            className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-foreground/10 transition-colors min-w-[1.75rem]"
            aria-label="Copy"
            title={copied ? 'Copied!' : 'Copy'}
          >
            {copied ? (
              <span className="text-[10px] font-medium">Copied</span>
            ) : (
              <Copy className="w-3.5 h-3.5" />
            )}
          </button>
        </div>
      )}
    </div>
  )

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div className={`flex items-end gap-2 ${isUser ? 'flex-row-reverse' : ''}`}>
        {avatar}
        {bubble}
      </div>
    </div>
  )
})
