import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useChatSession } from '@/contexts/chat-session-context'
import { ChatbotHeader } from './chatbot-header'
import { ChatbotMessages } from './chatbot-messages'
import { ChatbotFooter, type SendMessageOptions } from './chatbot-footer'
import { ChatbotButton } from './chatbot-button'
import { ChatbotSettings } from './chatbot-settings'
import { ChatbotEmailModal } from './chatbot-email-modal'
import {
  getLearningPreferences,
  postChat,
  postChatFeedback,
  postChatHandoff,
  putLearningPreferences,
} from '@/lib/api'
import { ChatFeedbackModal, type FeedbackModalPayload } from '@/components/chat-feedback-modal'
import { useAuthStore } from '@/stores/auth-store'
import advisorImage from '@/assets/images/Advisor.png'

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
  backendMessageId?: string
  feedbackType?: 'UP' | 'DOWN' | null
  isVoice?: boolean
  isVoiceResponse?: boolean
}

type View = 'chat' | 'settings'

const WELCOME_MESSAGE: Message = {
  id: 'welcome',
  role: 'assistant',
  content: "Hello! I'm OASIS HALO, your intelligent design companion. How can I help you create something amazing today?",
  timestamp: new Date(),
  feedbackType: null,
}

export function ChatbotWidget() {
  const navigate = useNavigate()
  const { mode, logout } = useAuthStore()
  const chatSession = useChatSession()
  const isGuest = mode === 'guest'

  const [isOpen, setIsOpen] = useState(false)
  const [currentView, setCurrentView] = useState<View>('chat')
  const [isEmailModalOpen, setIsEmailModalOpen] = useState(false)
  const [assistantAvatar, setAssistantAvatar] = useState<string>(advisorImage)
  const [messages, setMessages] = useState<Message[]>([WELCOME_MESSAGE])
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [isVoiceTurnLoading, setIsVoiceTurnLoading] = useState(false)
  const [isFeedbackModalOpen, setIsFeedbackModalOpen] = useState(false)
  const [feedbackTargetMessageId, setFeedbackTargetMessageId] = useState<string | null>(null)
  const [isSubmittingFeedback, setIsSubmittingFeedback] = useState(false)
  const [memoryConsentEnabled, setMemoryConsentEnabled] = useState(false)
  const [telemetryLearningEnabled, setTelemetryLearningEnabled] = useState(true)
  const [selectedLanguage, setSelectedLanguage] = useState('en')

  const patchMessageFeedback = useCallback((backendMessageId: string, feedbackType: 'UP' | 'DOWN') => {
    setMessages((prev) =>
      prev.map((message) =>
        message.backendMessageId === backendMessageId
          ? {
              ...message,
              feedbackType,
            }
          : message
      )
    )
  }, [])

  const handleRequireSignIn = useCallback(() => {
    logout()
    navigate('/login', { replace: true })
  }, [logout, navigate])

  useEffect(() => {
    if (isGuest) {
      setMemoryConsentEnabled(false)
      setTelemetryLearningEnabled(true)
      return
    }
    let cancelled = false
    getLearningPreferences()
      .then((prefs) => {
        if (cancelled) return
        setMemoryConsentEnabled(Boolean(prefs.long_term_personalization_opt_in))
        setTelemetryLearningEnabled(Boolean(prefs.telemetry_learning_opt_in))
      })
      .catch(() => {
        if (!cancelled) {
          setMemoryConsentEnabled(false)
          setTelemetryLearningEnabled(true)
        }
      })
    return () => {
      cancelled = true
    }
  }, [isGuest])

  const handleSendMessage = async (
    content: string,
    options?: SendMessageOptions
  ): Promise<string | void> => {
    const isVoice = options?.isVoice === true

    const userMessage: Message = {
      id: `user-${Date.now()}`,
      role: 'user',
      content,
      timestamp: new Date(),
      isVoice: isVoice || undefined,
    }
    setMessages((prev) => [...prev, userMessage])
    setIsLoading(true)
    if (isVoice) setIsVoiceTurnLoading(true)

    // Use shared session (from main chat) when available so both use same backend session
    const sessionToUse = chatSession?.sharedBackendSessionId ?? sessionId

    try {
      const response = await postChat(content, sessionToUse, selectedLanguage, isVoice)
      const newSessionId = response.session_id ?? null
      setSessionId(newSessionId)
      chatSession?.setSharedBackendSessionId(newSessionId)
      const assistantMessage: Message = {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content: response.content ?? '',
        timestamp: new Date(),
        backendMessageId: response.assistant_message_id ?? undefined,
        feedbackType: null,
        isVoiceResponse: isVoice || undefined,
      }
      setMessages((prev) => [...prev, assistantMessage])
      return response.content ?? ''
    } catch (err) {
      const errorContent =
        err instanceof Error ? err.message : 'Something went wrong. Please try again.'
      const errorMessage: Message = {
        id: `assistant-error-${Date.now()}`,
        role: 'assistant',
        content: errorContent,
        timestamp: new Date(),
      }
      setMessages((prev) => [...prev, errorMessage])
      return undefined
    } finally {
      setIsLoading(false)
      setIsVoiceTurnLoading(false)
    }
  }

  const handleFeedback = useCallback(
    async (messageId: string, feedbackType: 'UP' | 'DOWN') => {
      if (isGuest || !sessionId) {
        handleRequireSignIn()
        return
      }

      if (feedbackType === 'DOWN') {
        setFeedbackTargetMessageId(messageId)
        setIsFeedbackModalOpen(true)
        return
      }

      try {
        await postChatFeedback({
          session_id: sessionId,
          message_id: messageId,
          feedback_type: 'UP',
          reason_code: 'THUMBS_UP',
        })
        patchMessageFeedback(messageId, 'UP')
      } catch {
        // Keep chat usable even if feedback API fails.
      }
    },
    [handleRequireSignIn, isGuest, patchMessageFeedback, sessionId]
  )

  const handleSubmitNegativeFeedback = useCallback(
    async (payload: FeedbackModalPayload) => {
      if (!feedbackTargetMessageId || !sessionId) {
        setIsFeedbackModalOpen(false)
        return
      }
      setIsSubmittingFeedback(true)
      try {
        await postChatFeedback({
          session_id: sessionId,
          message_id: feedbackTargetMessageId,
          feedback_type: 'DOWN',
          reason_code: payload.reasonCode,
          correction_text: payload.correctionText || undefined,
          consent_long_term: payload.consentLongTerm,
        })
        patchMessageFeedback(feedbackTargetMessageId, 'DOWN')
        setFeedbackTargetMessageId(null)
        setIsFeedbackModalOpen(false)
      } catch {
        // Keep modal open so user can retry.
      } finally {
        setIsSubmittingFeedback(false)
      }
    },
    [feedbackTargetMessageId, patchMessageFeedback, sessionId]
  )

  const handleHandoff = useCallback(
    async (messageId: string) => {
      if (isGuest || !sessionId) {
        handleRequireSignIn()
        return
      }
      try {
        await postChatHandoff({
          session_id: sessionId,
          message_id: messageId,
          reason_code: 'USER_REQUEST',
        })
      } catch {
        // Handoff errors should not block chatting.
      }
    },
    [handleRequireSignIn, isGuest, sessionId]
  )

  const handleMemoryPreferenceChange = useCallback(
    async (enabled: boolean) => {
      if (isGuest) {
        handleRequireSignIn()
        return
      }
      setMemoryConsentEnabled(enabled)
      try {
        const updated = await putLearningPreferences({
          long_term_personalization_opt_in: enabled,
        })
        setMemoryConsentEnabled(Boolean(updated.long_term_personalization_opt_in))
      } catch {
        // Keep current local toggle to avoid blocking interaction on network failures.
      }
    },
    [handleRequireSignIn, isGuest]
  )

  const handleTelemetryPreferenceChange = useCallback(
    async (enabled: boolean) => {
      if (isGuest) {
        handleRequireSignIn()
        return
      }
      setTelemetryLearningEnabled(enabled)
      try {
        const updated = await putLearningPreferences({
          telemetry_learning_opt_in: enabled,
        })
        setTelemetryLearningEnabled(Boolean(updated.telemetry_learning_opt_in))
      } catch {
        // Keep current local toggle to avoid blocking interaction on network failures.
      }
    },
    [handleRequireSignIn, isGuest]
  )

  const handleClose = () => {
    setIsOpen(false)
    setCurrentView('chat')
  }

  const handleSettingsOpen = () => {
    setCurrentView('settings')
  }

  const handleSettingsClose = () => {
    setCurrentView('chat')
  }

  return (
    <>
      {!isOpen && <ChatbotButton onClick={() => setIsOpen(true)} />}
      {isOpen && (
        <div className="fixed bottom-4 right-4 z-50 w-full max-w-[440px] h-[700px] max-h-[90vh] sm:w-[440px]">
          <div className="relative w-full h-full bg-gradient-to-br from-[#F9FAFB] to-[#CDB7C4] border border-[#E5E7EB] rounded-lg shadow-2xl flex flex-col overflow-hidden">
            {currentView === 'chat' ? (
              <>
                <ChatbotHeader
                  onClose={handleClose}
                  onSettingsOpen={handleSettingsOpen}
                  onEmailOpen={() => setIsEmailModalOpen(true)}
                  currentAvatar={assistantAvatar}
                  onAvatarChange={setAssistantAvatar}
                  selectedLanguage={selectedLanguage}
                  onLanguageChange={setSelectedLanguage}
                />
                <ChatbotMessages
                  messages={messages}
                  assistantAvatar={assistantAvatar}
                  isLoading={isLoading}
                  isVoiceTurnLoading={isVoiceTurnLoading}
                  isGuest={isGuest}
                  onRequireSignIn={handleRequireSignIn}
                  onFeedback={handleFeedback}
                  onHandoff={handleHandoff}
                />
                <ChatbotFooter onSendMessage={handleSendMessage} disabled={isLoading} />
              </>
            ) : (
              <ChatbotSettings
                onBack={handleSettingsClose}
                memoryEnabled={memoryConsentEnabled}
                onMemoryChange={handleMemoryPreferenceChange}
                telemetryLearningEnabled={telemetryLearningEnabled}
                onTelemetryLearningChange={handleTelemetryPreferenceChange}
                privacyHint="Detailed trace and ops visibility are available in Main Chat debug panel."
              />
            )}

            {/* Email Modal - positioned above chatbot */}
            <ChatbotEmailModal
              isOpen={isEmailModalOpen}
              onClose={() => setIsEmailModalOpen(false)}
            />
          </div>
        </div>
      )}
      {isFeedbackModalOpen && (
        <ChatFeedbackModal
          isOpen={isFeedbackModalOpen}
          onClose={() => {
            setIsFeedbackModalOpen(false)
            setFeedbackTargetMessageId(null)
          }}
          onSubmit={handleSubmitNegativeFeedback}
          defaultConsentLongTerm={memoryConsentEnabled}
          isSubmitting={isSubmittingFeedback}
          title="Improve this widget response"
        />
      )}
    </>
  )
}
