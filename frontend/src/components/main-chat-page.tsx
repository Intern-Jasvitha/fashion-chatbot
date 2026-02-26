import { useState, useCallback, useEffect, useMemo, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { LogOut, Menu, PanelRightClose, PanelRightOpen, X } from 'lucide-react'
import { ChatSidebar, type ChatSession } from '@/components/chat-sidebar'
import { ChatContainer } from '@/components/chat-container'
import { ChatInput } from '@/components/chat-input'
import { useChatSession } from '@/contexts/chat-session-context'
import { useAuthStore } from '@/stores/auth-store'
import {
  type CanaryRollbackResponse,
  type CanaryStartResponse,
  type DebugTrace,
  type GoldenRunResponse,
  type LearningPreferences,
  type OpsDashboardResponse,
  type ReleaseStatusResponse,
  getChatHistory,
  getLearningPreferences,
  getOpsDashboard,
  getReleaseStatus,
  postChat,
  postChatFeedback,
  postChatHandoff,
  postReleaseCanaryRollback,
  postReleaseCanaryStart,
  postReleaseGoldenRun,
} from '@/lib/api'
import { Button } from '@/components/ui/button'
import { AgentDebugPanel } from '@/components/agent-debug-panel'
import { ChatFeedbackModal, type FeedbackModalPayload } from '@/components/chat-feedback-modal'

const STORAGE_KEY_SESSIONS = 'chat_sessions'
const STORAGE_KEY_CURRENT_SESSION = 'chat_current_session_id'

function loadSessionsFromStorage(): ChatSession[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY_SESSIONS)
    if (!raw) return []
    const parsed = JSON.parse(raw) as ChatSession[]
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function loadCurrentSessionIdFromStorage(): string {
  try {
    const id = localStorage.getItem(STORAGE_KEY_CURRENT_SESSION)
    return id ?? `${Date.now()}`
  } catch {
    return `${Date.now()}`
  }
}

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
  backendMessageId?: string
  feedbackType?: 'UP' | 'DOWN' | null
}

function formatSessionDate(d: Date): string {
  const now = new Date()
  const diffMs = now.getTime() - d.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMs / 3600000)
  const diffDays = Math.floor(diffMs / 86400000)
  if (diffMins < 1) return 'Just now'
  if (diffMins < 60) return `${diffMins}m ago`
  if (diffHours < 24) return `${diffHours}h ago`
  if (diffDays < 7) return `${diffDays} days ago`
  return d.toLocaleDateString()
}

export function MainChatPage() {
  const navigate = useNavigate()
  const { user, logout, mode } = useAuthStore()
  const chatSession = useChatSession()
  const isGuest = mode === 'guest'
  const [messages, setMessages] = useState<Message[]>([])
  const [sessions, setSessions] = useState<ChatSession[]>(() => (isGuest ? [] : loadSessionsFromStorage()))
  const [currentSessionId, setCurrentSessionId] = useState(() => (isGuest ? `${Date.now()}` : loadCurrentSessionIdFromStorage()))
  const [isLoading, setIsLoading] = useState(false)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [latestTrace, setLatestTrace] = useState<DebugTrace | null>(null)
  const [showDebugPanel, setShowDebugPanel] = useState(true)
  const [isFeedbackModalOpen, setIsFeedbackModalOpen] = useState(false)
  const [feedbackTargetMessageId, setFeedbackTargetMessageId] = useState<string | null>(null)
  const [isSubmittingFeedback, setIsSubmittingFeedback] = useState(false)
  const [isSubmittingHandoff, setIsSubmittingHandoff] = useState(false)
  const [defaultLongTermConsent, setDefaultLongTermConsent] = useState(false)
  const [learningPreferences, setLearningPreferences] = useState<LearningPreferences | null>(null)
  const [opsDashboard, setOpsDashboard] = useState<OpsDashboardResponse | null>(null)
  const [releaseStatus, setReleaseStatus] = useState<ReleaseStatusResponse | null>(null)
  const [latestGoldenRun, setLatestGoldenRun] = useState<GoldenRunResponse | null>(null)
  const [latestCanaryStart, setLatestCanaryStart] = useState<CanaryStartResponse | null>(null)
  const [latestCanaryRollback, setLatestCanaryRollback] = useState<CanaryRollbackResponse | null>(null)
  const [isRunningGoldenGate, setIsRunningGoldenGate] = useState(false)
  const [isStartingCanary, setIsStartingCanary] = useState(false)
  const [isRollingBackCanary, setIsRollingBackCanary] = useState(false)
  const initialSessionsRef = useRef(sessions)
  const initialSessionIdRef = useRef(currentSessionId)

  const handleLogout = useCallback(() => {
    logout()
    navigate('/login', { replace: true })
  }, [logout, navigate])

  const handleSignIn = useCallback(() => {
    logout()
    navigate('/login', { replace: true })
  }, [logout, navigate])

  useEffect(() => {
    if (!isGuest) {
      return
    }
    setSessions([])
    setCurrentSessionId(`${Date.now()}`)
    setMessages([])
    setLatestTrace(null)
    setLearningPreferences(null)
    setOpsDashboard(null)
    setReleaseStatus(null)
    localStorage.removeItem(STORAGE_KEY_SESSIONS)
    localStorage.removeItem(STORAGE_KEY_CURRENT_SESSION)
  }, [isGuest])

  // Persist sessions and currentSessionId to localStorage when they change.
  useEffect(() => {
    if (isGuest) return
    localStorage.setItem(STORAGE_KEY_SESSIONS, JSON.stringify(sessions))
  }, [isGuest, sessions])

  useEffect(() => {
    if (isGuest) return
    localStorage.setItem(STORAGE_KEY_CURRENT_SESSION, currentSessionId)
  }, [isGuest, currentSessionId])

  const activeBackendSessionId = useMemo(() => {
    if (isGuest) return null
    const current = sessions.find((s) => s.id === currentSessionId)
    return current?.backendSessionId ?? null
  }, [currentSessionId, isGuest, sessions])

  // Sync shared session context so the widget uses the same backend session.
  // Only set when main chat has a session; don't clear when user starts "New chat"
  // so the widget can keep its session until the user sends from main chat.
  useEffect(() => {
    if (chatSession?.setSharedBackendSessionId && activeBackendSessionId) {
      chatSession.setSharedBackendSessionId(activeBackendSessionId)
    }
  }, [activeBackendSessionId, chatSession?.setSharedBackendSessionId])

  const latestAssistantWithId = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i -= 1) {
      const message = messages[i]
      if (message.role === 'assistant' && message.backendMessageId) {
        return message
      }
    }
    return null
  }, [messages])

  // On mount (and when we have a restored current session with backend id), load its history.
  useEffect(() => {
    if (isGuest) {
      setMessages([])
      setLatestTrace(null)
      return
    }

    const initialSessions = initialSessionsRef.current
    const initialSessionId = initialSessionIdRef.current
    const session = initialSessions.find((s) => s.id === initialSessionId)
    if (!session?.backendSessionId) {
      setMessages([])
      return
    }
    let cancelled = false
    setHistoryLoading(true)
    getChatHistory(session.backendSessionId)
      .then((res) => {
        if (cancelled) return
        setMessages(
          res.messages.map((m) => ({
            id: m.id,
            role: m.role as 'user' | 'assistant',
            content: m.content,
            timestamp: new Date(m.created_at),
            backendMessageId: m.id,
            feedbackType: m.feedback_type ?? null,
          }))
        )
        setLatestTrace(res.latest_trace ?? null)
      })
      .catch(() => {
        if (!cancelled) {
          setMessages([])
          setLatestTrace(null)
        }
      })
      .finally(() => {
        if (!cancelled) setHistoryLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [isGuest])

  useEffect(() => {
    if (isGuest) {
      setDefaultLongTermConsent(false)
      return
    }
    let cancelled = false
    getLearningPreferences()
      .then((prefs) => {
        if (cancelled) return
        setLearningPreferences(prefs)
        setDefaultLongTermConsent(Boolean(prefs.long_term_personalization_opt_in))
      })
      .catch(() => {
        if (!cancelled) {
          setLearningPreferences(null)
          setDefaultLongTermConsent(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [isGuest])

  const handleSendMessage = useCallback(
    async (content: string) => {
      const wasFirstMessage = messages.length === 0
      const currentSession = sessions.find((s) => s.id === currentSessionId)
      const ownBackendSessionId = isGuest ? undefined : currentSession?.backendSessionId ?? undefined
      // Use shared session (from widget) when available so both use same backend session
      const backendSessionId =
        chatSession?.sharedBackendSessionId ?? ownBackendSessionId ?? undefined

      const userMessage: Message = {
        id: `user-${Date.now()}`,
        role: 'user',
        content,
        timestamp: new Date(),
      }

      setMessages((prev) => (isGuest ? [userMessage] : [...prev, userMessage]))
      setIsLoading(true)

      let response: Awaited<ReturnType<typeof postChat>> | null = null
      try {
        response = await postChat(content, backendSessionId)
        setLatestTrace(response.debug_trace ?? null)
        chatSession?.setSharedBackendSessionId(response.session_id ?? null)
        const assistantMessage: Message = {
          id: `assistant-${Date.now()}`,
          role: 'assistant',
          content: response.content,
          timestamp: new Date(),
          backendMessageId: response.assistant_message_id ?? undefined,
          feedbackType: null,
        }
        setMessages((prev) => (isGuest ? [userMessage, assistantMessage] : [...prev, assistantMessage]))
      } catch (err) {
        setLatestTrace(null)
        const errorContent =
          err instanceof Error ? err.message : 'Sorry, something went wrong. Please try again.'
        const errorMessage: Message = {
          id: `assistant-${Date.now()}`,
          role: 'assistant',
          content: errorContent,
          timestamp: new Date(),
        }
        setMessages((prev) => (isGuest ? [userMessage, errorMessage] : [...prev, errorMessage]))
      } finally {
        setIsLoading(false)
      }

      if (!isGuest && wasFirstMessage && response) {
        setSessions((prev) => {
          const title = content.slice(0, 40) + (content.length > 40 ? '…' : '')
          const newSession: ChatSession = {
            id: currentSessionId,
            title: title || 'New chat',
            date: formatSessionDate(new Date()),
            backendSessionId: response.session_id,
          }
          const exists = prev.some((s) => s.id === currentSessionId)
          if (exists) {
            return prev.map((s) =>
              s.id === currentSessionId
                ? {
                    ...s,
                    title: newSession.title,
                    date: newSession.date,
                    backendSessionId: newSession.backendSessionId,
                  }
                : s
            )
          }
          return [newSession, ...prev]
        })
      }
    },
    [messages.length, currentSessionId, sessions, isGuest, chatSession]
  )

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

  const handleRequireSignInForFeedback = useCallback(() => {
    handleSignIn()
  }, [handleSignIn])

  const handleFeedback = useCallback(
    async (backendMessageId: string, feedbackType: 'UP' | 'DOWN') => {
      if (isGuest || !activeBackendSessionId) {
        handleRequireSignInForFeedback()
        return
      }
      if (feedbackType === 'DOWN') {
        setFeedbackTargetMessageId(backendMessageId)
        setIsFeedbackModalOpen(true)
        return
      }
      try {
        await postChatFeedback({
          session_id: activeBackendSessionId,
          message_id: backendMessageId,
          feedback_type: 'UP',
          reason_code: 'THUMBS_UP',
        })
        patchMessageFeedback(backendMessageId, 'UP')
      } catch {
        // Keep chat usable even if feedback API fails.
      }
    },
    [activeBackendSessionId, handleRequireSignInForFeedback, isGuest, patchMessageFeedback]
  )

  const handleSubmitNegativeFeedback = useCallback(
    async (payload: FeedbackModalPayload) => {
      if (!feedbackTargetMessageId || !activeBackendSessionId) {
        setIsFeedbackModalOpen(false)
        return
      }
      setIsSubmittingFeedback(true)
      try {
        await postChatFeedback({
          session_id: activeBackendSessionId,
          message_id: feedbackTargetMessageId,
          feedback_type: 'DOWN',
          reason_code: payload.reasonCode,
          correction_text: payload.correctionText || undefined,
          consent_long_term: payload.consentLongTerm,
        })
        patchMessageFeedback(feedbackTargetMessageId, 'DOWN')
        setDefaultLongTermConsent(payload.consentLongTerm)
        setIsFeedbackModalOpen(false)
        setFeedbackTargetMessageId(null)
      } catch {
        // Keep modal open for retry on network/API failures.
      } finally {
        setIsSubmittingFeedback(false)
      }
    },
    [activeBackendSessionId, feedbackTargetMessageId, patchMessageFeedback]
  )

  const refreshDebugOps = useCallback(async () => {
    if (isGuest || !showDebugPanel) {
      return
    }
    try {
      const [dashboard, release] = await Promise.all([
        getOpsDashboard(7),
        getReleaseStatus(),
      ])
      setOpsDashboard(dashboard)
      setReleaseStatus(release)
    } catch {
      setOpsDashboard(null)
      setReleaseStatus(null)
    }
  }, [isGuest, showDebugPanel])

  useEffect(() => {
    void refreshDebugOps()
  }, [refreshDebugOps, latestTrace?.request_id])

  const handleRunGoldenGate = useCallback(async () => {
    if (isGuest || isRunningGoldenGate) return
    setIsRunningGoldenGate(true)
    try {
      const result = await postReleaseGoldenRun()
      setLatestGoldenRun(result)
      await refreshDebugOps()
    } catch {
      // Keep chat usable if ops control request fails.
    } finally {
      setIsRunningGoldenGate(false)
    }
  }, [isGuest, isRunningGoldenGate, refreshDebugOps])

  const handleStartCanary = useCallback(async () => {
    if (isGuest || isStartingCanary) return
    setIsStartingCanary(true)
    try {
      const result = await postReleaseCanaryStart({ experiment_dimension: 'wrqs_weights' })
      setLatestCanaryStart(result)
      await refreshDebugOps()
    } catch {
      // Keep chat usable if ops control request fails.
    } finally {
      setIsStartingCanary(false)
    }
  }, [isGuest, isStartingCanary, refreshDebugOps])

  const handleRollbackCanary = useCallback(async () => {
    if (isGuest || isRollingBackCanary) return
    setIsRollingBackCanary(true)
    try {
      const result = await postReleaseCanaryRollback({})
      setLatestCanaryRollback(result)
      await refreshDebugOps()
    } catch {
      // Keep chat usable if ops control request fails.
    } finally {
      setIsRollingBackCanary(false)
    }
  }, [isGuest, isRollingBackCanary, refreshDebugOps])

  const handleHandoff = useCallback(async () => {
    if (isGuest || !activeBackendSessionId || !latestAssistantWithId?.backendMessageId || isSubmittingHandoff) {
      if (isGuest) handleRequireSignInForFeedback()
      return
    }
    setIsSubmittingHandoff(true)
    try {
      await postChatHandoff({
        session_id: activeBackendSessionId,
        message_id: latestAssistantWithId.backendMessageId,
        reason_code: 'USER_REQUEST',
      })
    } catch {
      // Keep primary chat flow unaffected when handoff API fails.
    } finally {
      setIsSubmittingHandoff(false)
    }
  }, [
    activeBackendSessionId,
    handleRequireSignInForFeedback,
    isGuest,
    isSubmittingHandoff,
    latestAssistantWithId?.backendMessageId,
  ])

  const handleNewChat = useCallback(() => {
    setMessages([])
    setLatestTrace(null)
    const newSessionId = `${Date.now()}`
    setCurrentSessionId(newSessionId)
    setSidebarOpen(false)
  }, [])

  const handleSessionSelect = useCallback(
    async (id: string) => {
      if (isGuest) {
        return
      }
      setCurrentSessionId(id)
      const session = sessions.find((s) => s.id === id)
      if (session?.backendSessionId) {
        setHistoryLoading(true)
        try {
          const res = await getChatHistory(session.backendSessionId)
          setMessages(
            res.messages.map((m) => ({
              id: m.id,
              role: m.role as 'user' | 'assistant',
              content: m.content,
              timestamp: new Date(m.created_at),
              backendMessageId: m.id,
              feedbackType: m.feedback_type ?? null,
            }))
          )
          setLatestTrace(res.latest_trace ?? null)
        } catch {
          setMessages([])
          setLatestTrace(null)
        } finally {
          setHistoryLoading(false)
        }
      } else {
        setMessages([])
        setLatestTrace(null)
      }
    },
    [sessions, isGuest]
  )

  const handleSessionDelete = useCallback(
    (id: string) => {
      if (isGuest) {
        return
      }
      setSessions((prev) => prev.filter((s) => s.id !== id))
      if (currentSessionId === id) {
        setMessages([])
        setLatestTrace(null)
        setCurrentSessionId(`${Date.now()}`)
      }
    },
    [currentSessionId, isGuest]
  )

  return (
    <div className="flex h-screen bg-background overflow-hidden grain">
      {!isGuest && (
        <ChatSidebar
          sessions={sessions}
          currentSessionId={currentSessionId}
          onSessionSelect={handleSessionSelect}
          onSessionDelete={handleSessionDelete}
          onNewChat={handleNewChat}
          isOpen={sidebarOpen}
          onClose={() => setSidebarOpen(false)}
        />
      )}

      <div className="flex-1 flex min-h-0">
        <div className="flex-1 flex flex-col overflow-hidden relative z-0 min-w-0">
          <header className="border-b border-border/80 bg-card/80 backdrop-blur-sm px-4 md:px-8 py-4 flex items-center justify-between min-h-[4rem]">
            <div className="flex items-center gap-3">
              {!isGuest && (
                <button
                  onClick={() => setSidebarOpen(!sidebarOpen)}
                  className="md:hidden p-2.5 -ml-1 rounded-lg text-muted-foreground hover:text-foreground hover:bg-secondary/50 transition-colors duration-200"
                  aria-label={sidebarOpen ? 'Close sidebar' : 'Open sidebar'}
                >
                  {sidebarOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
                </button>
              )}
              <div>
                <h1 className="text-[1.25rem] font-semibold text-foreground tracking-tight [font-family:var(--font-display)]">
                  Dress Design Assistant
                </h1>
                <p className="text-xs text-muted-foreground mt-0.5 font-light">
                  Creative & personalized styling guidance
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={handleHandoff}
                disabled={!latestAssistantWithId?.backendMessageId || isSubmittingHandoff}
                className="hidden xl:inline-flex gap-1.5 text-muted-foreground hover:text-foreground disabled:opacity-50"
                aria-label="Escalate latest answer to human review"
              >
                {isSubmittingHandoff ? 'Escalating...' : 'Handoff'}
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setShowDebugPanel((prev) => !prev)}
                className="hidden xl:inline-flex gap-1.5 text-muted-foreground hover:text-foreground"
                aria-label={showDebugPanel ? 'Hide execution trace panel' : 'Show execution trace panel'}
              >
                {showDebugPanel ? <PanelRightClose className="w-4 h-4" /> : <PanelRightOpen className="w-4 h-4" />}
                Trace
              </Button>
              {!isGuest && user && (
                <span className="text-xs text-muted-foreground hidden sm:inline truncate max-w-[10rem]" title={user.email}>
                  {user.name || user.email}
                </span>
              )}
              {isGuest ? (
                <Button variant="ghost" size="sm" onClick={handleSignIn} className="gap-1.5 text-muted-foreground hover:text-foreground">
                  Sign in
                </Button>
              ) : (
                <Button variant="ghost" size="sm" onClick={handleLogout} className="gap-1.5 text-muted-foreground hover:text-foreground">
                  <LogOut className="w-4 h-4" />
                  Log out
                </Button>
              )}
            </div>
          </header>

          {isGuest && (
            <div className="border-b border-border/70 bg-secondary/35 px-4 md:px-8 py-2.5 flex items-center justify-between gap-3">
              <p className="text-xs text-muted-foreground">
                Guest mode: public OASIS info only. Chat is not saved and each prompt is one-off.
              </p>
              <Button type="button" size="sm" variant="secondary" onClick={handleSignIn}>
                Sign in for full access
              </Button>
            </div>
          )}

          <ChatContainer
            messages={messages}
            isLoading={isLoading || historyLoading}
            isGuest={isGuest}
            onFeedback={handleFeedback}
            onRequireSignIn={handleRequireSignInForFeedback}
          />
          <ChatInput onSubmit={handleSendMessage} isLoading={isLoading} />
        </div>
        {showDebugPanel && (
          <AgentDebugPanel
            trace={latestTrace}
            learningPreferences={learningPreferences}
            opsDashboard={opsDashboard}
            releaseStatus={releaseStatus}
            latestGoldenRun={latestGoldenRun}
            latestCanaryStart={latestCanaryStart}
            latestCanaryRollback={latestCanaryRollback}
            onRunGoldenGate={handleRunGoldenGate}
            onStartCanary={handleStartCanary}
            onRollbackCanary={handleRollbackCanary}
            isRunningGoldenGate={isRunningGoldenGate}
            isStartingCanary={isStartingCanary}
            isRollingBackCanary={isRollingBackCanary}
          />
        )}
      </div>
      {isFeedbackModalOpen && (
        <ChatFeedbackModal
          isOpen={isFeedbackModalOpen}
          onClose={() => {
            setIsFeedbackModalOpen(false)
            setFeedbackTargetMessageId(null)
          }}
          onSubmit={handleSubmitNegativeFeedback}
          defaultConsentLongTerm={defaultLongTermConsent}
          isSubmitting={isSubmittingFeedback}
        />
      )}
    </div>
  )
}
