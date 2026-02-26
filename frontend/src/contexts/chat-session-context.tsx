import { createContext, useCallback, useContext, useState } from 'react'

interface ChatSessionContextValue {
  sharedBackendSessionId: string | null
  setSharedBackendSessionId: (id: string | null) => void
}

const ChatSessionContext = createContext<ChatSessionContextValue | null>(null)

export function ChatSessionProvider({ children }: { children: React.ReactNode }) {
  const [sharedBackendSessionId, setSharedBackendSessionId] = useState<string | null>(null)
  return (
    <ChatSessionContext.Provider
      value={{
        sharedBackendSessionId,
        setSharedBackendSessionId,
      }}
    >
      {children}
    </ChatSessionContext.Provider>
  )
}

export function useChatSession() {
  const ctx = useContext(ChatSessionContext)
  return ctx
}
