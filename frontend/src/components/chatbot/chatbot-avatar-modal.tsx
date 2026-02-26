import { useState, useEffect } from 'react'
import { X, Check } from 'lucide-react'
import advisorImage from '@/assets/images/Advisor.png'
import aiAssistantImage from '@/assets/images/AI-Assistant.png'
import designerImage from '@/assets/images/Designer.png'
import fashionExpertImage from '@/assets/images/Fashion-Expert.png'
import stylistImage from '@/assets/images/Stylist.png'
import creativeImage from '@/assets/images/Creative.png'

interface ChatbotAvatarModalProps {
  isOpen: boolean
  onClose: () => void
  onAvatarSelect: (avatarId: string) => void
  currentAvatar: string
}

// All avatars in a single list
const allAvatars = [
  { id: 'ai-assistant', name: 'AI Assistant', image: aiAssistantImage },
  { id: 'advisor', name: 'Advisor', image: advisorImage },
  { id: 'designer', name: 'Designer', image: designerImage },
  { id: 'fashion-expert', name: 'Fashion Expert', image: fashionExpertImage },
  { id: 'stylist', name: 'Stylist', image: stylistImage },
  { id: 'creative', name: 'Creative', image: creativeImage },
]

// Map avatar IDs to their images
const avatarImageMap: Record<string, string> = {
  'advisor': advisorImage,
  'ai-assistant': aiAssistantImage,
  'designer': designerImage,
  'fashion-expert': fashionExpertImage,
  'stylist': stylistImage,
  'creative': creativeImage,
}

export function ChatbotAvatarModal({ isOpen, onClose, onAvatarSelect, currentAvatar }: ChatbotAvatarModalProps) {
  // Find current avatar ID from image path
  const getCurrentAvatarId = (avatar: string) => {
    for (const [id, image] of Object.entries(avatarImageMap)) {
      if (image === avatar) return id
    }
    return 'advisor' // default
  }
  
  const [selectedAvatar, setSelectedAvatar] = useState(() => getCurrentAvatarId(currentAvatar))

  // Update selected avatar when modal opens or currentAvatar changes
  useEffect(() => {
    if (isOpen) {
      setSelectedAvatar(getCurrentAvatarId(currentAvatar))
    }
  }, [isOpen, currentAvatar])

  if (!isOpen) return null

  const handleAvatarClick = (avatarId: string) => {
    setSelectedAvatar(avatarId)
  }

  const handleConfirm = () => {
    onAvatarSelect(selectedAvatar)
    onClose()
  }

  return (
    <div className="absolute inset-0 z-[60] flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden="true"
      />
      
      {/* Avatar Modal */}
      <div className="relative w-full max-w-md bg-white rounded-lg shadow-2xl overflow-hidden z-10 mx-4">
        {/* Header */}
        <div className="bg-[#460B2F] px-6 py-4 flex items-center justify-between">
          <div>
            <h2 className="text-xl font-bold text-white">Choose Your Avatar</h2>
            <p className="text-xs text-white/80 mt-1">Select a personality for OASIS HALO</p>
          </div>
          <button
            onClick={onClose}
            className="w-6 h-6 flex items-center justify-center text-white hover:bg-white/20 rounded transition-colors shrink-0"
            aria-label="Close avatar modal"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
        
        {/* Content */}
        <div className="px-3 py-3">
          {/* Avatar Grid */}
          <div className="grid grid-cols-2 gap-4">
            {allAvatars.map((avatar) => (
              <button
                key={avatar.id}
                onClick={() => handleAvatarClick(avatar.id)}
                className={`relative p-2 rounded-xl border-2 transition-colors text-center ${
                  selectedAvatar === avatar.id
                    ? 'border-[#460B2F] bg-purple-50'
                    : 'border-gray-200 bg-white hover:border-gray-300'
                }`}
              >
                {/* Checkmark for selected */}
                {selectedAvatar === avatar.id && (
                  <div className="absolute top-2 right-2 w-5 h-5 bg-[#460B2F] rounded-full flex items-center justify-center">
                    <Check className="w-3 h-3 text-white" />
                  </div>
                )}
                
                {/* Avatar Image */}
                <div className="w-16 h-16 mx-auto mb-2 rounded-full overflow-hidden bg-gray-100">
                  <img
                    src={avatar.image}
                    alt={avatar.name}
                    className="w-full h-full object-cover"
                  />
                </div>
                
                {/* Avatar Name */}
                <p className="text-sm font-medium text-gray-900">{avatar.name}</p>
              </button>
            ))}
          </div>
        </div>
        
        {/* Footer Button */}
        <div className="px-6 py-4 border-t border-gray-200 bg-gray-50">
          <button
            onClick={handleConfirm}
            className="w-full bg-[#460B2F] text-white py-3 rounded-lg font-medium hover:bg-[#460B2F]/90 transition-colors"
          >
            Confirm Selection
          </button>
        </div>
      </div>
    </div>
  )
}
