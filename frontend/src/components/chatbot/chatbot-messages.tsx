import { useEffect, useRef } from 'react'
import type { Message } from './chatbot-widget'
import { ChatbotMessage } from './chatbot-message'
import advisorImage from '@/assets/images/Advisor.png'

interface ChatbotMessagesProps {
  messages: Message[]
  assistantAvatar?: string
  isLoading?: boolean
  isVoiceTurnLoading?: boolean
  isGuest?: boolean
  onRequireSignIn?: () => void
  onFeedback?: (messageId: string, feedbackType: 'UP' | 'DOWN') => void | Promise<void>
  onHandoff?: (messageId: string) => void | Promise<void>
}

function TypingLoader({ avatar }: { avatar: string }) {
  return (
    <div className="flex gap-3 items-start">
      <div className="flex-shrink-0 relative">
        <div className="w-10 h-10 rounded-full bg-white shadow-[0px_10px_15px_-3px_rgba(0,0,0,0.1),0px_4px_6px_-4px_rgba(0,0,0,0.1)] flex items-center justify-center">
          <div className="w-8 h-8 rounded-full overflow-hidden">
            <img
              src={avatar || advisorImage}
              alt="Assistant"
              className="w-full h-full object-cover"
            />
          </div>
        </div>
        <div className="absolute top-6 left-7 w-3.5 h-3.5 bg-[#00BBA7] border-2 border-white rounded-full" />
      </div>
      <div className="bg-[#F3F4F6] rounded-3xl rounded-tl-[10px] px-6 py-4 max-w-[305px]">
        <div className="flex items-center gap-1.5">
          <span
            className="w-2 h-2 rounded-full bg-[#6A7282] animate-[typing-bounce_1.4s_ease-in-out_infinite]"
            style={{ animationDelay: '0ms' }}
          />
          <span
            className="w-2 h-2 rounded-full bg-[#6A7282] animate-[typing-bounce_1.4s_ease-in-out_infinite]"
            style={{ animationDelay: '200ms' }}
          />
          <span
            className="w-2 h-2 rounded-full bg-[#6A7282] animate-[typing-bounce_1.4s_ease-in-out_infinite]"
            style={{ animationDelay: '400ms' }}
          />
        </div>
      </div>
    </div>
  )
}

function VoiceLoader({ avatar }: { avatar: string }) {
  return (
    <div className="flex gap-3 items-start">
      <div className="flex-shrink-0 relative">
        <div className="w-10 h-10 rounded-full bg-white shadow-[0px_10px_15px_-3px_rgba(0,0,0,0.1),0px_4px_6px_-4px_rgba(0,0,0,0.1)] flex items-center justify-center">
          <div className="w-8 h-8 rounded-full overflow-hidden">
            <img
              src={avatar || advisorImage}
              alt="Assistant"
              className="w-full h-full object-cover"
            />
          </div>
        </div>
        <div className="absolute top-6 left-7 w-3.5 h-3.5 bg-[#00BBA7] border-2 border-white rounded-full" />
      </div>
      <div className="bg-[#F3F4F6] rounded-3xl rounded-tl-[10px] px-6 py-4 max-w-[305px]">
        <div className="flex items-end gap-1 h-8">
          <span
            className="w-2 h-6 rounded-full bg-[#6A7282] origin-bottom animate-[voice-wave_0.8s_ease-in-out_infinite]"
          />
          <span
            className="w-2 h-8 rounded-full bg-[#6A7282] origin-bottom animate-[voice-wave_0.8s_ease-in-out_infinite]"
            style={{ animationDelay: '0.1s' }}
          />
          <span
            className="w-2 h-5 rounded-full bg-[#6A7282] origin-bottom animate-[voice-wave_0.8s_ease-in-out_infinite]"
            style={{ animationDelay: '0.2s' }}
          />
          <span
            className="w-2 h-7 rounded-full bg-[#6A7282] origin-bottom animate-[voice-wave_0.8s_ease-in-out_infinite]"
            style={{ animationDelay: '0.3s' }}
          />
          <span
            className="w-2 h-4 rounded-full bg-[#6A7282] origin-bottom animate-[voice-wave_0.8s_ease-in-out_infinite]"
            style={{ animationDelay: '0.4s' }}
          />
        </div>
        <p className="text-[#6A7282] text-xs mt-2">Speaking...</p>
      </div>
    </div>
  )
}

export function ChatbotMessages({
  messages,
  assistantAvatar,
  isLoading = false,
  isVoiceTurnLoading = false,
  isGuest = false,
  onRequireSignIn,
  onFeedback,
  onHandoff,
}: ChatbotMessagesProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading])

  return (
    <div className="flex-1 overflow-y-auto px-4 pt-4 pb-0 scrollbar-thin scrollbar-thumb-gray-300 scrollbar-track-transparent">
      <div className="flex flex-col gap-2">
        {messages.map((message) => (
          <ChatbotMessage
            key={message.id}
            message={message}
            assistantAvatar={assistantAvatar}
            isGuest={isGuest}
            onRequireSignIn={onRequireSignIn}
            onFeedback={onFeedback}
            onHandoff={onHandoff}
          />
        ))}
        {isLoading &&
          (isVoiceTurnLoading ? (
            <VoiceLoader avatar={assistantAvatar ?? ''} />
          ) : (
            <TypingLoader avatar={assistantAvatar ?? ''} />
          ))}
        <div ref={messagesEndRef} />
      </div>
    </div>
  )
}
