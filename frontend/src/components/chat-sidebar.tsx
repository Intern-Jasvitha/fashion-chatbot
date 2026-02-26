import { Button } from '@/components/ui/button'
import { Plus, Trash2, X } from 'lucide-react'
import React, { useCallback } from 'react'

export interface ChatSession {
  id: string
  title: string
  date: string
  backendSessionId?: string
}

interface ChatSidebarProps {
  sessions: ChatSession[]
  currentSessionId?: string
  onSessionSelect: (id: string) => void
  onSessionDelete: (id: string) => void
  onNewChat: () => void
  isOpen?: boolean
  onClose?: () => void
}

export function ChatSidebar({
  sessions,
  currentSessionId,
  onSessionSelect,
  onSessionDelete,
  onNewChat,
  isOpen = true,
  onClose,
}: ChatSidebarProps) {
  const handleDelete = useCallback(
    (id: string, e: React.MouseEvent) => {
      e.stopPropagation()
      onSessionDelete(id)
    },
    [onSessionDelete]
  )

  return (
    <>
      {isOpen && (
        <div
          className="fixed inset-0 bg-foreground/20 backdrop-blur-[2px] md:hidden z-40 animate-in fade-in duration-200"
          onClick={onClose}
          aria-hidden
        />
      )}

      <aside
        className={`fixed md:relative top-0 left-0 h-screen w-[17rem] md:w-72 bg-sidebar border-r border-sidebar-border flex flex-col transition-[transform] duration-300 ease-out z-50 md:z-0 ${
          isOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'
        }`}
      >
        <div className="p-5 pb-4 border-b border-sidebar-border">
          <div className="flex items-start justify-between gap-2">
            <div>
              <h2 className="text-lg font-semibold text-sidebar-foreground tracking-tight [font-family:var(--font-display)]">
                Dress AI
              </h2>
              <p className="text-xs text-muted-foreground mt-0.5 font-light">
                Design Assistant
              </p>
            </div>
            {onClose && (
              <button
                className="md:hidden p-2 -mr-1 rounded-lg text-muted-foreground hover:text-foreground hover:bg-sidebar-accent transition-colors"
                onClick={onClose}
                aria-label="Close sidebar"
              >
                <X className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>

        <div className="p-4">
          <Button
            onClick={onNewChat}
            className="w-full rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground font-medium h-10 gap-2 shadow-sm"
          >
            <Plus className="w-4 h-4" />
            New Chat
          </Button>
        </div>

        <div className="flex-1 overflow-y-auto px-3 pb-6">
          <p className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider px-2 py-2.5">
            Recent Chats
          </p>
          <ul className="space-y-0.5">
            {sessions.map((session) => (
              <li key={session.id}>
                <div
                  role="button"
                  tabIndex={0}
                  onClick={() => {
                    onSessionSelect(session.id)
                    onClose?.()
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      onSessionSelect(session.id)
                      onClose?.()
                    }
                  }}
                  className={`group flex items-start gap-2 p-3 rounded-lg cursor-pointer transition-colors duration-200 ${
                    currentSessionId === session.id
                      ? 'bg-sidebar-accent text-sidebar-accent-foreground'
                      : 'hover:bg-sidebar-accent/60 text-sidebar-foreground'
                  }`}
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate leading-snug">
                      {session.title}
                    </p>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {session.date}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={(e) => handleDelete(session.id, e)}
                    className="flex-shrink-0 p-1.5 rounded-md opacity-0 group-hover:opacity-100 focus:opacity-100 transition-opacity text-muted-foreground hover:text-destructive"
                    aria-label={`Delete ${session.title}`}
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </div>

        <div className="p-4 pt-3 border-t border-sidebar-border">
          <p className="text-[11px] text-muted-foreground font-light">
            © 2026 Dress AI · Your personal design assistant
          </p>
        </div>
      </aside>
    </>
  )
}
