import React, { useState, useRef, useEffect } from 'react'
import { Send } from 'lucide-react'
import { Textarea } from '@/components/ui/textarea'

interface ChatInputProps {
  onSubmit: (message: string) => void
  isLoading?: boolean
}

export function ChatInput({ onSubmit, isLoading = false }: ChatInputProps) {
  const [input, setInput] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 140) + 'px'
    }
  }, [input])

  const handleSubmit = (e?: React.FormEvent) => {
    e?.preventDefault()
    if (input.trim() && !isLoading) {
      onSubmit(input)
      setInput('')
      if (textareaRef.current) textareaRef.current.style.height = 'auto'
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="border-t border-border/80 bg-card/60 backdrop-blur-sm px-4 md:px-8 py-4 md:py-5"
    >
      <div className="max-w-3xl mx-auto flex gap-2 items-end">
        <div className="flex-shrink-0 flex items-center gap-1 pb-3">
        </div>
        <div className="flex-1 min-w-0">
          <Textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="What's on your mind?"
            className="min-h-[3rem] max-h-36 resize-none rounded-xl border-border/80 bg-background/80 focus:border-primary/40 focus:ring-2 focus:ring-primary/10 text-foreground placeholder:text-muted-foreground/70 py-3 px-4 text-sm font-light transition-colors duration-200 w-full"
            rows={1}
            disabled={isLoading}
          />
        </div>
        <button
          type="submit"
          disabled={!input.trim() || isLoading}
          className="flex-shrink-0 w-12 h-12 rounded-full bg-primary hover:bg-primary/90 text-primary-foreground flex items-center justify-center shadow-sm transition-all duration-200 disabled:opacity-50 disabled:pointer-events-none"
          aria-label="Send message"
        >
          <Send className="w-4 h-4" strokeWidth={2} />
        </button>
      </div>
    </form>
  )
}
