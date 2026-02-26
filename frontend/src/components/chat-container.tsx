import { useCallback, useEffect, useRef } from 'react'
import { ChatMessage } from '@/components/chat-message'

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
  backendMessageId?: string
  feedbackType?: 'UP' | 'DOWN' | null
}

interface ChatContainerProps {
  messages: Message[]
  isLoading?: boolean
  isGuest?: boolean
  onFeedback?: (messageId: string, feedbackType: 'UP' | 'DOWN') => void | Promise<void>
  onRequireSignIn?: () => void
}

function getMessageGroupFlags(messages: Message[], index: number) {
  const current = messages[index]
  const prev = messages[index - 1]
  const next = messages[index + 1]
  const isConsecutive = prev?.role === current.role
  const isLastInGroup = next?.role !== current.role
  return { isConsecutive, isLastInGroup }
}

/* rendering-hoist-jsx: Extract static empty state outside component */
const ChatEmptyState = () => (
  <div className="flex-1 flex items-center justify-center px-6 py-16">
    <div className="text-center max-w-sm animate-in fade-in duration-500">
      <div
        className="w-14 h-14 rounded-2xl flex items-center justify-center mx-auto mb-5 border border-border/60 bg-card/50"
        aria-hidden
      >
        <svg
          className="w-7 h-7 text-primary/80"
          fill="none"
          stroke="currentColor"
          strokeWidth={1.5}
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 00-2.456 2.456z"
          />
        </svg>
      </div>
      <h2 className="text-xl font-semibold text-foreground tracking-tight [font-family:var(--font-display)] mb-2">
        Welcome to Dress AI
      </h2>
      <p className="text-muted-foreground text-sm font-light leading-relaxed mb-8">
        Your personal design assistant. Describe your style, occasion, or ask for inspiration to get started.
      </p>
      <div className="text-left">
        <p className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider mb-2">
          Try asking
        </p>
        <ul className="space-y-2 text-sm text-muted-foreground font-light">
          <li className="flex items-center gap-2">
            <span className="w-1 h-1 rounded-full bg-primary/60" />
            What&apos;s the best fabric for a summer wedding?
          </li>
          <li className="flex items-center gap-2">
            <span className="w-1 h-1 rounded-full bg-primary/60" />
            Design a dress for a casual brunch
          </li>
          <li className="flex items-center gap-2">
            <span className="w-1 h-1 rounded-full bg-primary/60" />
            Suggest colors for my body type
          </li>
        </ul>
      </div>
    </div>
  </div>
)

export function ChatContainer({
  messages,
  isLoading = false,
  isGuest = false,
  onFeedback,
  onRequireSignIn,
}: ChatContainerProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [])

  useEffect(() => {
    scrollToBottom()
  }, [messages, scrollToBottom])

  if (messages.length === 0) {
    return <ChatEmptyState />
  }

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-3xl mx-auto px-4 md:px-8 py-6">
        {messages.map((message, index) => {
          const { isConsecutive, isLastInGroup } = getMessageGroupFlags(messages, index)
          return (
            <div
              key={message.id}
              className="chat-message-item animate-in fade-in slide-in-from-bottom-2 duration-300"
              style={{ animationDelay: `${Math.min(index * 40, 120)}ms` }}
            >
              <ChatMessage
                id={message.id}
                role={message.role}
                content={message.content}
                timestamp={message.timestamp}
                backendMessageId={message.backendMessageId}
                feedbackType={message.feedbackType ?? null}
                onFeedback={onFeedback}
                onRequireSignIn={onRequireSignIn}
                isGuest={isGuest}
                isConsecutive={isConsecutive}
                isLastInGroup={isLastInGroup}
              />
            </div>
          )
        })}
        {isLoading && (
          <div className="flex justify-start animate-in fade-in duration-200 mt-4">
            <div className="flex items-end gap-2">
              <div className="flex-shrink-0 w-8 h-8 sm:w-9 sm:h-9 rounded-full flex items-center justify-center bg-foreground/10">
                <span className="text-[10px] sm:text-xs font-semibold">AI</span>
              </div>
              <div
                className="rounded-2xl px-4 py-3 max-w-[85%] sm:max-w-[28rem]"
                style={{
                  backgroundColor: 'var(--msg-assistant-bg)',
                  borderWidth: '1px',
                  borderColor: 'var(--msg-assistant-border)',
                }}
              >
                <div className="flex gap-1">
                  <span className="w-2 h-2 rounded-full bg-foreground/50 animate-bounce [animation-delay:0ms]" />
                  <span className="w-2 h-2 rounded-full bg-foreground/50 animate-bounce [animation-delay:150ms]" />
                  <span className="w-2 h-2 rounded-full bg-foreground/50 animate-bounce [animation-delay:300ms]" />
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
      <div ref={messagesEndRef} />
    </div>
  )
}
