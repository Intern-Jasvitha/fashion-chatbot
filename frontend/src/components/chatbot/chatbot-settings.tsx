import { useState } from 'react'
import { X, Lock, Brain, FileText, MessageSquare, ChevronRight } from 'lucide-react'

interface ChatbotSettingsProps {
  onBack?: () => void
  memoryEnabled?: boolean
  onMemoryChange?: (enabled: boolean) => void
  telemetryLearningEnabled?: boolean
  onTelemetryLearningChange?: (enabled: boolean) => void
  privacyHint?: string
}

interface ToggleSwitchProps {
  enabled: boolean
  onChange: (enabled: boolean) => void
}

function ToggleSwitch({ enabled, onChange }: ToggleSwitchProps) {
  return (
    <button
      type="button"
      onClick={() => onChange(!enabled)}
      className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-[#460B2F] focus:ring-offset-2 ${
        enabled ? 'bg-[#460B2F]' : 'bg-gray-300'
      }`}
      role="switch"
      aria-checked={enabled}
    >
      <span
        className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
          enabled ? 'translate-x-6' : 'translate-x-1'
        }`}
      />
    </button>
  )
}

interface SettingItemProps {
  icon: React.ReactNode
  iconBg: string
  title: string
  description: string
  toggle?: {
    enabled: boolean
    onChange: (enabled: boolean) => void
  }
  onClick?: () => void
}

function SettingItem({ icon, iconBg, title, description, toggle, onClick }: SettingItemProps) {
  return (
    <div
      className={`flex items-center gap-4 p-2 rounded-xl bg-gray-100 ${
        onClick ? 'cursor-pointer hover:bg-gray-50' : ''
      }`}
      onClick={onClick}
    >
      {/* Icon */}
      <div className={`w-12 h-12 rounded-3xl flex items-center justify-center ${iconBg} flex-shrink-0`}>
        {icon}
      </div>
      
      {/* Content */}
      <div className="flex-1 min-w-0">
        <h3 className="text-sm font-semibold text-gray-900">{title}</h3>
        <p className="text-xs text-gray-600 mt-0.5">{description}</p>
      </div>
      
      {/* Toggle or Chevron */}
      {toggle ? (
        <ToggleSwitch enabled={toggle.enabled} onChange={toggle.onChange} />
      ) : (
        <ChevronRight className="w-5 h-5 text-gray-400 flex-shrink-0" />
      )}
    </div>
  )
}

export function ChatbotSettings({
  onBack,
  memoryEnabled = true,
  onMemoryChange,
  telemetryLearningEnabled = true,
  onTelemetryLearningChange,
  privacyHint = 'Detailed trace and ops visibility are available in Main Chat debug panel.',
}: ChatbotSettingsProps) {
  const [autoSpell, setAutoSpell] = useState(false)

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-white">
      {/* Settings Header */}
      <div className="bg-[#460B2F] px-6 py-5 flex items-start justify-between">
        <div>
          <h2 className="text-xl font-bold text-white">Settings</h2>
          <p className="text-sm text-white/80 mt-1">Customize your OASIS HALO experience</p>
        </div>
        {onBack && (
          <button
            onClick={onBack}
            className="w-6 h-6 flex items-center justify-center text-white hover:bg-white/20 rounded transition-colors shrink-0"
            aria-label="Back to chat"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>
      
      {/* Content */}
      <div className="flex-1 overflow-y-auto px-6 py-6 space-y-6">
          {/* Privacy & Data Section */}
          <div>
            <h3 className="text-base font-bold text-gray-900 mb-4">Privacy & Data</h3>
            <div className="space-y-3">
              <SettingItem
                icon={<Lock className="w-5 h-5 text-blue-600" />}
                iconBg="bg-blue-100"
                title="Learning Telemetry"
                description="Allow anonymized learning signals"
                toggle={{
                  enabled: telemetryLearningEnabled,
                  onChange: (enabled) => onTelemetryLearningChange?.(enabled),
                }}
              />
              <SettingItem
                icon={<Brain className="w-6 h-6 text-purple-600" />}
                iconBg="bg-purple-100"
                title="Memory"
                description="For enhanced support"
                toggle={{
                  enabled: memoryEnabled,
                  onChange: (enabled) => onMemoryChange?.(enabled),
                }}
              />
              <SettingItem
                icon={<FileText className="w-6 h-6 text-orange-600" />}
                iconBg="bg-orange-100"
                title="Auto Spell"
                description="Fixes errors instantly as you type."
                toggle={{
                  enabled: autoSpell,
                  onChange: setAutoSpell,
                }}
              />
            </div>
          </div>
          
          {/* Support Section */}
          <div>
            <h3 className="text-base font-bold text-gray-900 mb-4">Support</h3>
            <div className="space-y-3">
              <SettingItem
                icon={<MessageSquare className="w-6 h-6 text-green-600" />}
                iconBg="bg-green-100"
                title="Feedback"
                description={privacyHint}
                onClick={() => {
                  // Handle feedback click
                  console.log('Feedback clicked')
                }}
              />
              <SettingItem
                icon={<FileText className="w-6 h-6 text-gray-600" />}
                iconBg="bg-gray-100"
                title="Privacy and Data Policy"
                description=""
                onClick={() => {
                  // Handle privacy policy click
                  console.log('Privacy policy clicked')
                }}
              />
            </div>
          </div>
        </div>
        
      {/* Footer */}
        <div className="px-6 py-4">
            <div className="border-t border-gray-200 mx-8"></div>

            <p className="text-center text-sm text-gray-600 mt-4">
                OASIS HALO v1.0.0
            </p>
        </div>
    </div>
  )
}
