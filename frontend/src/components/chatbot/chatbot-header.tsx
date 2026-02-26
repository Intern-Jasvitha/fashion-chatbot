import { useState, useEffect, useRef } from 'react'
import { X, Pencil, Check, Volume2 } from 'lucide-react'
import advisorImage from '@/assets/images/Advisor.png'
import aiAssistantImage from '@/assets/images/AI-Assistant.png'
import designerImage from '@/assets/images/Designer.png'
import fashionExpertImage from '@/assets/images/Fashion-Expert.png'
import stylistImage from '@/assets/images/Stylist.png'
import creativeImage from '@/assets/images/Creative.png'
import { ChatbotAvatarModal } from './chatbot-avatar-modal'
import elegantFemaleImage from '@/assets/images/elegant-female.png'
import calmMaleImage from '@/assets/images/calm-male.png'
import professionalNeutralImage from '@/assets/images/professional-neutral.png'
import expressiveYouthfulImage from '@/assets/images/expressive-youthful.png'
import whisperLuxuryImage from '@/assets/images/whisker.png'
import arrowDownIcon from '@/assets/icons/arrow-down.svg'
import globeIcon from '@/assets/icons/globe.svg'
import messageIcon from '@/assets/icons/message.svg'
import settingsIcon from '@/assets/icons/settings.svg'

interface ChatbotHeaderProps {
  onClose: () => void
  onSettingsOpen?: () => void
  onEmailOpen?: () => void
  currentAvatar?: string
  onAvatarChange?: (avatarSrc: string) => void
  selectedLanguage: string
  onLanguageChange: (code: string) => void
}

const languages = [
  { code: 'en', name: 'English', nativeName: 'English' },
  { code: 'hi', name: 'Hindi', nativeName: 'हिन्दी' },
  { code: 'bn', name: 'Bengali', nativeName: 'বাংলা' },
  { code: 'mr', name: 'Marathi', nativeName: 'मराठी' },
  { code: 'te', name: 'Telugu', nativeName: 'తెలుగు' },
]

const voices = [
  { id: 'elegant-female', name: 'Elegant Female', image: elegantFemaleImage },
  { id: 'calm-male', name: 'Calm Male', image: calmMaleImage },
  { id: 'professional-neutral', name: 'Professional Neutral', image: professionalNeutralImage },
  { id: 'expressive-youthful', name: 'Expressive Youthful', image: expressiveYouthfulImage },
  { id: 'whisper-luxury', name: 'Whisper Luxury', image: whisperLuxuryImage },
]

export function ChatbotHeader({ onClose, onSettingsOpen, onEmailOpen, currentAvatar, onAvatarChange, selectedLanguage, onLanguageChange }: ChatbotHeaderProps) {
  const [isLanguageDropdownOpen, setIsLanguageDropdownOpen] = useState(false)
  const [isVoiceDropdownOpen, setIsVoiceDropdownOpen] = useState(false)
  const [isAvatarModalOpen, setIsAvatarModalOpen] = useState(false)
  const [isSpeakerOn, setIsSpeakerOn] = useState(true)
  const [selectedVoice, setSelectedVoice] = useState('elegant-female')
  const languageDropdownRef = useRef<HTMLDivElement>(null)
  const languageButtonRef = useRef<HTMLButtonElement>(null)
  const voiceDropdownRef = useRef<HTMLDivElement>(null)
  const voiceButtonRef = useRef<HTMLButtonElement>(null)

  // Close language dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        languageDropdownRef.current &&
        !languageDropdownRef.current.contains(event.target as Node) &&
        languageButtonRef.current &&
        !languageButtonRef.current.contains(event.target as Node)
      ) {
        setIsLanguageDropdownOpen(false)
      }
    }

    if (isLanguageDropdownOpen) {
      document.addEventListener('mousedown', handleClickOutside)
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [isLanguageDropdownOpen])

  // Close voice dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        voiceDropdownRef.current &&
        !voiceDropdownRef.current.contains(event.target as Node) &&
        voiceButtonRef.current &&
        !voiceButtonRef.current.contains(event.target as Node)
      ) {
        setIsVoiceDropdownOpen(false)
      }
    }

    if (isVoiceDropdownOpen) {
      document.addEventListener('mousedown', handleClickOutside)
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [isVoiceDropdownOpen])
  return (
    <div className="bg-[#460B2F] flex items-start gap-4 p-0.5">
      {/* Left Section: Avatar Image */}
        <div className="relative flex-shrink-0 w-24 h-28">
            <img 
                src={currentAvatar || advisorImage} 
                alt="User avatar" 
                className="w-full h-full object-cover bg-[#D9D9D9]"
            />

            {/* Edit button overlay */}
            <button
              onClick={() => setIsAvatarModalOpen(true)}
              className="absolute top-2 -right-0 bg-white rounded-full 
                            flex items-center justify-center 
                            cursor-pointer shadow-md 
                            w-5 h-5 z-10 hover:bg-gray-100 transition-colors"
              aria-label="Edit avatar"
            >
                <Pencil 
                className="w-3.5 h-3.5 text-[#460B2F]" 
                strokeWidth={1.5} 
                />
            </button>
        </div>


      {/* Right Section: Content and Controls */}
      <div className="flex-1 flex flex-col gap-10 min-w-0">
        {/* Top row: Title and Close button */}
        <div className="flex items-center justify-between gap-3">
          {/* Title */}
          <div className="text-white font-bold leading-6 text-sm">
            OASIS HALO - <span className="italic font-normal text-xs">Your Intelligent AI Companion</span>
          </div>
          
          {/* Close button */}
          <button
            onClick={onClose}
            className="w-7 h-7 flex items-center justify-center text-white hover:bg-white/20 rounded transition-colors flex-shrink-0"
            aria-label="Close chat"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Bottom row: Control buttons - aligned to right */}
        <div className="flex items-center justify-end gap-2 px-2 h-7 w-full">
          {/* Voice button with dropdown */}
          <div className="relative">
            <button
              ref={voiceButtonRef}
              onClick={() => setIsVoiceDropdownOpen(!isVoiceDropdownOpen)}
              className="flex items-center text-white rounded-xl hover:opacity-80 transition-opacity bg-white/20 px-2 py-1.5 h-6 text-xs font-medium gap-1"
              aria-label="Select voice"
            >
              <span>Voice</span>
              <img src={arrowDownIcon} alt="dropdown" className="w-3 h-3" />
            </button>
            
            {/* Voice Dropdown */}
            {isVoiceDropdownOpen && (
              <div
                ref={voiceDropdownRef}
                className="absolute right-0 top-8 mt-1 bg-white rounded-lg shadow-lg min-w-[280px] z-50"
              >
                <div className="px-4 py-3 border-b border-gray-200">
                  <h3 className="text-sm font-semibold text-gray-900">Select Voice</h3>
                </div>
                <div className="py-2">
                  {voices.map((voice) => (
                    <button
                      key={voice.id}
                      onClick={() => {
                        setSelectedVoice(voice.id)
                        setIsVoiceDropdownOpen(false)
                      }}
                      className={`w-full px-3 py-1 flex items-center gap-3 transition-colors ${
                        selectedVoice === voice.id
                          ? 'bg-gray-50 border-2 border-gray-300 rounded-lg'
                          : 'hover:bg-gray-50'
                      }`}
                    >
                      {/* Voice Icon */}
                      <div className="w-12 h-12 rounded-full flex-shrink-0 overflow-hidden">
                        <img
                          src={voice.image}
                          alt={voice.name}
                          className="w-full h-full object-cover"
                        />
                      </div>
                      
                      {/* Voice Name */}
                      <span
                        className={`flex-1 text-sm font-medium ${
                          selectedVoice === voice.id
                            ? 'text-[#8B2E3E]'
                            : 'text-gray-900'
                        }`}
                      >
                        {voice.name}
                      </span>
                      
                      {/* Checkmark for selected */}
                      {selectedVoice === voice.id && (
                        <Check className="w-5 h-5 text-gray-700" />
                      )}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
          
          {/* Globe icon with language dropdown */}
          <div className="relative">
            <button
              ref={languageButtonRef}
              onClick={() => setIsLanguageDropdownOpen(!isLanguageDropdownOpen)}
              className="w-7 h-7 flex items-center justify-center rounded-xl hover:opacity-80 transition-opacity bg-white/20"
              aria-label="Select language"
            >
              <img src={globeIcon} alt="globe" className="w-4 h-4" />
            </button>
            
            {/* Language Dropdown */}
            {isLanguageDropdownOpen && (
              <div
                ref={languageDropdownRef}
                className="absolute right-0 top-8 mt-1 bg-white rounded-lg shadow-lg border border-gray-200 min-w-[200px] max-h-[200px] overflow-y-auto z-50"
              >
                <div className="px-4 py-3 border-b border-gray-200">
                  <h3 className="text-sm font-semibold text-gray-900">Select Language</h3>
                </div>
                <div className="py-1">
                  {languages.map((language) => (
                    <button
                      key={language.code}
                      onClick={() => {
                        onLanguageChange(language.code)
                        setIsLanguageDropdownOpen(false)
                      }}
                      className={`w-full px-4 py-2 text-left text-sm flex items-center justify-between hover:bg-gray-50 transition-colors ${
                        selectedLanguage === language.code
                          ? 'bg-[#460B2F] text-white hover:bg-[#460B2F]/90'
                          : 'text-gray-900'
                      }`}
                    >
                      <span>
                        {language.name} - {language.nativeName}
                      </span>
                      {selectedLanguage === language.code && (
                        <Check className="w-4 h-4 text-white" />
                      )}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
          
          {/* Speaker icon with toggle and online indicator */}
          <button
            onClick={() => setIsSpeakerOn(!isSpeakerOn)}
            className="relative w-7 h-7 flex items-center justify-center rounded-xl hover:opacity-80 transition-opacity bg-white/20"
            aria-label={isSpeakerOn ? 'Turn speaker off' : 'Turn speaker on'}
          >
            <Volume2 className={`w-4 h-4 ${isSpeakerOn ? 'text-white' : 'text-gray-400'}`} />
            {isSpeakerOn && (
              <div className="absolute bg-[#14B8A6] rounded-full border border-white w-1.5 h-1.5 -top-0.5 right-0.5"></div>
            )}
          </button>
          
          {/* Message/Email icon */}
          <button
            onClick={onEmailOpen}
            className="relative w-7 h-7 flex items-center justify-center rounded-xl hover:opacity-80 transition-opacity bg-white/20"
            aria-label="Send email"
          >
            <img src={messageIcon} alt="email" className="w-4 h-4" />
          </button>
          
          {/* Settings icon */}
          <button
            onClick={onSettingsOpen}
            className="w-7 h-7 flex items-center justify-center rounded-xl hover:opacity-80 transition-opacity bg-white/20"
            aria-label="Open settings"
          >
            <img src={settingsIcon} alt="settings" className="w-4 h-4" />
          </button>
        </div>
      </div>
      
      {/* Avatar Selection Modal */}
      <ChatbotAvatarModal
        isOpen={isAvatarModalOpen}
        onClose={() => setIsAvatarModalOpen(false)}
        onAvatarSelect={(avatarId) => {
          if (!onAvatarChange) return
          // Map avatar ID to image
          const avatarMap: Record<string, string> = {
            'advisor': advisorImage,
            'ai-assistant': aiAssistantImage,
            'designer': designerImage,
            'fashion-expert': fashionExpertImage,
            'stylist': stylistImage,
            'creative': creativeImage,
          }
          onAvatarChange(avatarMap[avatarId] || advisorImage)
        }}
        currentAvatar={currentAvatar || advisorImage}
      />
    </div>
  )
}
