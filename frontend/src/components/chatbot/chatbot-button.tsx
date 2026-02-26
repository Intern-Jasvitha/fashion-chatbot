import { MessageSquare } from 'lucide-react'

interface ChatbotButtonProps {
  onClick: () => void
}

export function ChatbotButton({ onClick }: ChatbotButtonProps) {
  return (
    <button
      onClick={onClick}
      className="fixed bottom-6 right-6 w-14 h-14 bg-gradient-to-br from-[#51A2FF] to-[#00D3F3] rounded-full shadow-[0px_10px_15px_-3px_rgba(0,0,0,0.1),0px_4px_6px_-4px_rgba(0,0,0,0.1)] flex items-center justify-center text-white hover:scale-105 transition-transform duration-200 z-50"
      aria-label="Open chat"
    >
      <MessageSquare className="w-6 h-6" />
    </button>
  )
}
