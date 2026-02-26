import { useState } from 'react'
import { X, Mail } from 'lucide-react'

interface ChatbotEmailModalProps {
  isOpen: boolean
  onClose: () => void
}

type ContentOption = 'full-chat' | 'design-summary' | 'recommendation-only'

export function ChatbotEmailModal({ isOpen, onClose }: ChatbotEmailModalProps) {
  const [email, setEmail] = useState('')
  const [selectedContent, setSelectedContent] = useState<ContentOption>('full-chat')

  if (!isOpen) return null

  const handleSend = () => {
    if (!email.trim()) return
    // Handle email send logic here
    console.log('Sending email to:', email, 'Content:', selectedContent)
    onClose()
  }

  const contentOptions = [
    {
      id: 'full-chat' as ContentOption,
      title: 'Full Chat',
      description: 'Complete conversation history',
    },
    {
      id: 'design-summary' as ContentOption,
      title: 'Design Summary',
      description: 'Key decisions and recommendations',
    },
    {
      id: 'recommendation-only' as ContentOption,
      title: 'Recommendation Only',
      description: 'Final design suggestions',
    },
  ]

  return (
    <div className="absolute inset-0 z-[60] flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden="true"
      />
      
      {/* Email Modal */}
      <div className="relative w-full max-w-md bg-white rounded-lg shadow-2xl overflow-hidden z-10 mx-4">
        {/* Header */}
        <div className="bg-[#460B2F] px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Mail className="w-5 h-5 text-white" />
            <div>
              <h2 className="text-lg font-bold text-white">Email Conversation</h2>
              <p className="text-xs text-white/80 mt-0.5">Choose what to send</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-6 h-6 flex items-center justify-center text-white hover:bg-white/20 rounded transition-colors shrink-0"
            aria-label="Close email modal"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
        
        {/* Content */}
        <div className="px-3 py-3 space-y-6">
          {/* Email Address Input */}
          <div>
            <label className="block text-sm font-medium text-gray-900 mb-2">
              Email Address
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="your@email.com"
              className="w-full px-4 py-2.5 border border-gray-300 rounded-lg bg-gray-50 focus:outline-none focus:ring-2 focus:ring-[#460B2F] focus:border-transparent text-sm"
            />
          </div>
          
          {/* Content to Send */}
          <div>
            <label className="block text-sm font-medium text-gray-900 mb-3">
              Content to Send
            </label>
            <div className="space-y-3">
              {contentOptions.map((option) => (
                <button
                  key={option.id}
                  onClick={() => setSelectedContent(option.id)}
                  className={`w-full p-2 rounded-lg border-2 text-left transition-colors ${
                    selectedContent === option.id
                      ? 'border-[#460B2F] bg-purple-50'
                      : 'border-gray-200 bg-white hover:border-gray-300'
                  }`}
                >
                  <div className="flex items-start gap-3">
                    {/* Radio Button */}
                    <div className="mt-0.5">
                      <div
                        className={`w-5 h-5 rounded-full border-2 flex items-center justify-center ${
                          selectedContent === option.id
                            ? 'border-[#460B2F] bg-[#460B2F]'
                            : 'border-gray-300'
                        }`}
                      >
                        {selectedContent === option.id && (
                          <div className="w-2 h-2 rounded-full bg-white" />
                        )}
                      </div>
                    </div>
                    
                    {/* Content */}
                    <div className="flex-1">
                      <h3 className="text-sm font-semibold text-gray-900">{option.title}</h3>
                      <p className="text-xs text-gray-600 mt-0.5">{option.description}</p>
                    </div>
                  </div>
                </button>
              ))}
            </div>
          </div>
        </div>
        
        {/* Footer Button */}
        <div className="px-4 py-4">
          <button
            onClick={handleSend}
            disabled={!email.trim()}
            className="w-full bg-[#460B2F] text-white py-3 rounded-lg font-medium hover:bg-[#460B2F]/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Send Email
          </button>
        </div>
      </div>
    </div>
  )
}
