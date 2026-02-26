import { useState, type KeyboardEvent } from 'react'
import { Mic, PhoneOff, Send } from 'lucide-react'
import { useAgentVoice } from '@/hooks/use-agent-voice'

export interface SendMessageOptions {
  isVoice?: boolean
}

interface ChatbotFooterProps {
  onSendMessage: (content: string, options?: SendMessageOptions) => void | Promise<string | void>
  disabled?: boolean
}

export function ChatbotFooter({ onSendMessage, disabled = false }: ChatbotFooterProps) {
  const [message, setMessage] = useState('')
  const [isVoiceMode, setIsVoiceMode] = useState(false)

  const { startListening, stopListening, speakResponse, setProcessing, status, isSupported } =
    useAgentVoice({
      onTranscriptReady: async (transcript) => {
        setProcessing()
        try {
          const response = await onSendMessage(transcript, { isVoice: true })
          if (response?.trim()) {
            await speakResponse(response)
          }
        } catch (err) {
          console.error('Voice agent error:', err)
        }
      },
      onError: (error) => {
        console.error('Voice error:', error)
        setIsVoiceMode(false)
      },
    })

  const handleVoiceToggle = () => {
    if (isVoiceMode) {
      stopListening()
      setIsVoiceMode(false)
    } else {
      if (!isSupported) {
        console.error('Speech recognition not supported')
        return
      }
      setIsVoiceMode(true)
      startListening()
    }
  }

  const handleSend = () => {
    if (message.trim() && !disabled) {
      onSendMessage(message.trim())
      setMessage('')
    }
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const voiceStatusLabel =
    status === 'listening'
      ? 'Listening...'
      : status === 'processing'
        ? 'Processing...'
        : status === 'speaking'
          ? 'AI is speaking...'
          : status === 'error'
            ? 'Error - tap to retry'
            : 'Tap mic to speak'

  return (
    <div className="bg-white border-t border-[#E5E7EB] px-3 py-4 min-h-[100px] flex items-center">
      <div className="px-3 py-2 flex items-center gap-2 w-full">
        {/* Voice button */}
        <button
          onClick={handleVoiceToggle}
          disabled={disabled || !isSupported}
          className={`w-8 h-8 flex items-center justify-center rounded-full transition-colors shrink-0 ${
            isVoiceMode
              ? 'bg-red-500 hover:bg-red-600 animate-pulse'
              : 'hover:bg-gray-200'
          } disabled:opacity-50 disabled:cursor-not-allowed`}
          aria-label={isVoiceMode ? 'Stop voice' : 'Start voice'}
        >
          {isVoiceMode ? (
            <PhoneOff className="w-4 h-4 text-white" />
          ) : (
            <Mic className="w-4 h-4 text-[#4A5565]" />
          )}
        </button>

        {/* Input field or voice status */}
        {isVoiceMode ? (
          <div className="flex-1 min-w-0">
            <div className="text-sm text-red-500 font-medium">{voiceStatusLabel}</div>
          </div>
        ) : (
          <input
            type="text"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type a message..."
            disabled={disabled}
            className="flex-1 bg-transparent border-none outline-none text-sm text-[#1E2939] placeholder:text-[#99A1AF] disabled:opacity-50 min-w-0"
          />
        )}

        {/* Send button (only in text mode) */}
        {!isVoiceMode && (
          <button
            onClick={handleSend}
            disabled={!message.trim() || disabled}
            className={`w-8 h-8 rounded-full flex items-center justify-center transition-colors shrink-0 ${
              message.trim() && !disabled
                ? 'bg-red-500 hover:bg-red-600'
                : 'bg-[#E5E7EB] hover:bg-[#D1D5DB]'
            } disabled:opacity-50 disabled:cursor-not-allowed`}
            aria-label="Send message"
          >
            <Send
              className={`w-4 h-4 ${message.trim() && !disabled ? 'text-white' : 'text-[#99A1AF]'}`}
            />
          </button>
        )}
      </div>
    </div>
  )
}
