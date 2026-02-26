import { useState, type KeyboardEvent } from 'react'
import { Mic, MicOff, Send, X, Check } from 'lucide-react'

interface ChatbotFooterProps {
  onSendMessage: (content: string) => void
  disabled?: boolean
}

type FooterState = 'default' | 'listening' | 'recording' | 'has-message'

export function ChatbotFooter({ onSendMessage, disabled = false }: ChatbotFooterProps) {
  const [message, setMessage] = useState('')
  const [state, setState] = useState<FooterState>('default')

  const handleSend = () => {
    if (message.trim() && !disabled) {
      onSendMessage(message.trim())
      setMessage('')
      setState('default')
    }
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleMicClick = () => {
    if (state === 'default') {
      setState('listening')
      // Simulate voice recognition - in real app, this would start voice input
      setTimeout(() => {
        setState('recording')
      }, 500)
    } else if (state === 'recording') {
      setState('default')
    }
  }

  const handleListeningCancel = () => {
    setState('default')
    setMessage('')
  }

  const handleListeningConfirm = () => {
    if (message.trim()) {
      handleSend()
    } else {
      setState('default')
    }
  }

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setMessage(e.target.value)
    if (e.target.value.trim()) {
      setState('has-message')
    } else if (state === 'has-message') {
      setState('default')
    }
  }

  // Sound wave icon component
  const SoundWaveIcon = ({ className }: { className?: string }) => (
    <div className={`flex items-center gap-0.5 ${className || ''}`}>
      <div className="w-0.5 h-2 bg-current rounded-full"></div>
      <div className="w-0.5 h-3 bg-current rounded-full"></div>
      <div className="w-0.5 h-4 bg-current rounded-full"></div>
    </div>
  )

  return (
    <div className="bg-white border-t border-[#E5E7EB] px-3 py-4 min-h-[100px] flex items-center">
      <div className="px-3 py-2 flex items-center gap-2 w-full">
        {/* Microphone button */}
        {state === 'listening' ? (
          <div className="flex items-center gap-1.5 shrink-0">
            <MicOff className="w-4 h-4 text-red-500" />
            <SoundWaveIcon className="text-red-500" />
          </div>
        ) : (
          <button
            onClick={handleMicClick}
            className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-gray-200 transition-colors shrink-0"
            aria-label="Start voice input"
          >
            <Mic className="w-4 h-4 text-[#4A5565]" />
          </button>
        )}
        
        {/* Input field or listening text */}
        {state === 'listening' ? (
          <div className="flex-1 text-sm text-red-500">Listening...</div>
        ) : (
          <input
            type="text"
            value={message}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            placeholder="Type a message..."
            className="flex-1 bg-transparent border-none outline-none text-sm text-[#1E2939] placeholder:text-[#99A1AF]"
          />
        )}
        
        {/* Right side buttons - varies by state */}
        {state === 'listening' ? (
          <div className="flex items-center gap-2 shrink-0">
            <button
              onClick={handleListeningCancel}
              className="w-6 h-6 flex items-center justify-center rounded-full hover:bg-gray-200 transition-colors"
              aria-label="Cancel"
            >
              <X className="w-4 h-4 text-[#4A5565]" />
            </button>
            <button
              onClick={handleListeningConfirm}
              className="w-6 h-6 flex items-center justify-center rounded-full hover:bg-gray-200 transition-colors"
              aria-label="Confirm"
            >
              <Check className="w-4 h-4 text-[#4A5565]" />
            </button>
          </div>
        ) : state === 'recording' ? (
          <button
            onClick={handleMicClick}
            className="px-3 py-1.5 bg-red-500 text-white rounded-lg flex items-center gap-1.5 hover:bg-red-600 transition-colors shrink-0"
            aria-label="End recording"
          >
            <SoundWaveIcon className="text-white" />
            <span className="text-xs font-medium">End</span>
          </button>
        ) : (
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
            <Send className={`w-4 h-4 ${message.trim() && !disabled ? 'text-white' : 'text-[#99A1AF]'}`} />
          </button>
        )}
      </div>
    </div>
  )
}
