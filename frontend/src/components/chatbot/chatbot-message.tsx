import type { Message } from './chatbot-widget'
import { LifeBuoy, ThumbsDown, ThumbsUp } from 'lucide-react'
import advisorImage from '@/assets/images/Advisor.png'

interface ChatbotMessageProps {
  message: Message
  assistantAvatar?: string
  isGuest?: boolean
  onRequireSignIn?: () => void
  onFeedback?: (messageId: string, feedbackType: 'UP' | 'DOWN') => void | Promise<void>
  onHandoff?: (messageId: string) => void | Promise<void>
}

function formatTimestamp(date: Date): string {
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  
  if (diffMins < 1) return 'Just now'
  if (diffMins < 60) return `${diffMins}m ago`
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

export function ChatbotMessage({
  message,
  assistantAvatar,
  isGuest = false,
  onRequireSignIn,
  onFeedback,
  onHandoff,
}: ChatbotMessageProps) {
  const isAssistant = message.role === 'assistant'
  
  if (isAssistant) {
    return (
      <div className="flex gap-3 items-start">
        {/* Avatar */}
        <div className="flex-shrink-0 relative">
          <div className="w-10 h-10 rounded-full bg-white shadow-[0px_10px_15px_-3px_rgba(0,0,0,0.1),0px_4px_6px_-4px_rgba(0,0,0,0.1)] flex items-center justify-center">
            <div className="w-8 h-8 rounded-full overflow-hidden">
              <img
                src={assistantAvatar || advisorImage}
                alt="Assistant avatar"
                className="w-full h-full object-cover"
              />
            </div>
          </div>
          <div className="absolute top-6 left-7 w-3.5 h-3.5 bg-[#00BBA7] border-2 border-white rounded-full"></div>
        </div>
        
        {/* Message bubble */}
        <div className="flex-1 flex flex-col gap-2 min-w-0">
          <div className="bg-[#F3F4F6] rounded-3xl rounded-tl-[10px] px-6 pt-4 pb-3 max-w-[305px]">
            <p className="text-[#1E2939] text-sm leading-[23px] font-normal">
              {message.content}
            </p>
          </div>
          
          {/* Timestamp and feedback */}
          <div className="flex items-center gap-2">
            <span className="text-[#6A7282] text-xs leading-4">
              {formatTimestamp(message.timestamp)}
            </span>
            <div className="flex items-center gap-2">
              <button
                className="w-8 h-8 flex items-center justify-center rounded-xl hover:bg-gray-100 transition-colors"
                title={isGuest ? 'Sign in to submit feedback' : 'Helpful'}
                onClick={() => {
                  if (isGuest) {
                    onRequireSignIn?.()
                    return
                  }
                  if (message.backendMessageId) onFeedback?.(message.backendMessageId, 'UP')
                }}
              >
                <ThumbsUp
                  className={`w-4 h-4 ${message.feedbackType === 'UP' ? 'text-green-600' : 'text-[#99A1AF]'}`}
                  strokeWidth={1.33333}
                />
              </button>
              <button
                className="w-8 h-8 flex items-center justify-center rounded-xl hover:bg-gray-100 transition-colors"
                title={isGuest ? 'Sign in to submit feedback' : 'Needs improvement'}
                onClick={() => {
                  if (isGuest) {
                    onRequireSignIn?.()
                    return
                  }
                  if (message.backendMessageId) onFeedback?.(message.backendMessageId, 'DOWN')
                }}
              >
                <ThumbsDown
                  className={`w-4 h-4 ${message.feedbackType === 'DOWN' ? 'text-red-600' : 'text-[#99A1AF]'}`}
                  strokeWidth={1.33333}
                />
              </button>
              <button
                className="w-8 h-8 flex items-center justify-center rounded-xl hover:bg-gray-100 transition-colors"
                title={isGuest ? 'Sign in to request handoff' : 'Escalate to human review'}
                onClick={() => {
                  if (isGuest) {
                    onRequireSignIn?.()
                    return
                  }
                  if (message.backendMessageId) onHandoff?.(message.backendMessageId)
                }}
              >
                <LifeBuoy className="w-4 h-4 text-[#99A1AF]" strokeWidth={1.33333} />
              </button>
            </div>
          </div>
        </div>
      </div>
    )
  }
  
  // User message (right aligned)
  return (
    <div className="flex justify-end">
      <div className="bg-[#F3F4F6] rounded-3xl rounded-tr-[10px] px-6 pt-4 pb-3 max-w-[305px]">
        <p className="text-[#1E2939] text-sm leading-[23px] font-normal">
          {message.content}
        </p>
      </div>
    </div>
  )
}
