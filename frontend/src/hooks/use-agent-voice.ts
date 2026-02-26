import { useCallback, useRef, useState } from 'react'
import { postTTS } from '@/lib/api'

export type AgentVoiceStatus = 'idle' | 'listening' | 'processing' | 'speaking' | 'error'

interface UseAgentVoiceConfig {
  onTranscriptReady: (transcript: string) => void
  onError?: (error: string) => void
  onStatusChange?: (status: AgentVoiceStatus) => void
}

declare global {
  interface Window {
    SpeechRecognition?: typeof SpeechRecognition
    webkitSpeechRecognition?: typeof SpeechRecognition
  }
}

const SpeechRecognitionAPI =
  typeof window !== 'undefined'
    ? window.SpeechRecognition ?? window.webkitSpeechRecognition
    : undefined

const MAX_NO_SPEECH_RETRIES = 2

export function useAgentVoice(config: UseAgentVoiceConfig) {
  const [status, setStatus] = useState<AgentVoiceStatus>('idle')
  const statusRef = useRef<AgentVoiceStatus>('idle')
  const recognitionRef = useRef<SpeechRecognition | null>(null)
  const noSpeechRetriesRef = useRef(0)
  const configRef = useRef(config)
  configRef.current = config

  const updateStatus = useCallback((s: AgentVoiceStatus) => {
    statusRef.current = s
    setStatus(s)
    configRef.current.onStatusChange?.(s)
  }, [])

  const startListening = useCallback(() => {
    if (!SpeechRecognitionAPI) {
      configRef.current.onError?.('Speech recognition is not supported in this browser.')
      updateStatus('error')
      return
    }

    noSpeechRetriesRef.current = 0

    const startRecognition = () => {
      const recognition = new SpeechRecognitionAPI()
      recognition.continuous = true
      recognition.interimResults = true
      recognition.lang = 'en-US'

      recognition.onstart = () => {
        updateStatus('listening')
      }

      recognition.onresult = (event: SpeechRecognitionEvent) => {
        const results = event.results
        const lastResult = results[results.length - 1]
        const transcript = lastResult?.[0]?.transcript?.trim()
        if (transcript && lastResult?.isFinal) {
          recognition.stop()
          configRef.current.onTranscriptReady(transcript)
        }
      }

      recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
        if (event.error === 'no-speech') {
          if (noSpeechRetriesRef.current < MAX_NO_SPEECH_RETRIES) {
            noSpeechRetriesRef.current += 1
            setTimeout(() => {
              if (statusRef.current === 'listening') {
                startRecognition()
              }
            }, 300)
          } else {
            recognitionRef.current = null
            updateStatus('idle')
          }
          return
        }
        configRef.current.onError?.(event.error || 'Speech recognition error')
        updateStatus('error')
      }

      recognition.onend = () => {
        if (statusRef.current !== 'processing' && statusRef.current !== 'speaking') {
          recognitionRef.current = null
          updateStatus('idle')
        }
      }

      recognitionRef.current = recognition
      recognition.start()
    }

    startRecognition()
  }, [updateStatus])

  const stopListening = useCallback(() => {
    if (recognitionRef.current) {
      recognitionRef.current.abort()
      recognitionRef.current = null
    }
    if (statusRef.current === 'listening') {
      updateStatus('idle')
    }
  }, [updateStatus])

  const speakResponse = useCallback(
    async (text: string) => {
      if (!text?.trim()) return

      try {
        updateStatus('speaking')
        const audioBuffer = await postTTS(text)
        const blob = new Blob([audioBuffer], { type: 'audio/mpeg' })
        const url = URL.createObjectURL(blob)
        const audio = new Audio(url)

        await new Promise<void>((resolve, reject) => {
          audio.onended = () => {
            URL.revokeObjectURL(url)
            resolve()
          }
          audio.onerror = () => {
            URL.revokeObjectURL(url)
            reject(new Error('Audio playback failed'))
          }
          audio.play().catch(reject)
        })

        updateStatus('idle')
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'TTS failed'
        configRef.current.onError?.(msg)
        updateStatus('error')
      }
    },
    [updateStatus]
  )

  const setProcessing = useCallback(() => updateStatus('processing'), [updateStatus])

  const isSupported = Boolean(SpeechRecognitionAPI)

  return {
    startListening,
    stopListening,
    speakResponse,
    setProcessing,
    status,
    isSupported,
  }
}
