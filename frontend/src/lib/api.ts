import { getToken, useAuthStore } from '@/stores/auth-store'

const API_BASE = import.meta.env.VITE_API_URL ?? ''

function authHeaders(): HeadersInit {
  const token = getToken()
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  return headers
}

function handleResponse(res: Response): void {
  if (res.status === 401) {
    useAuthStore.getState().logout()
    window.location.href = '/login'
  }
}

export interface ChatResponse {
  content: string
  intent: string
  session_id: string
  assistant_message_id?: string | null
  request_id: string
  turn_index: number
  debug_trace?: DebugTrace | null
}

export interface TraceStep {
  step: string
  agent: string
  status: string
  summary: string
  duration_ms?: number | null
  details?: Record<string, unknown>
}

export interface DebugTrace {
  request_id: string
  user_query: string
  intent?: 'sql' | 'rag' | 'hybrid' | null
  called_agents: string[]
  steps: TraceStep[]
  created_at: string
}

export interface ChatMessageOut {
  id: string
  role: string
  content: string
  created_at: string
  feedback_type?: 'UP' | 'DOWN' | null
}

export interface ChatHistoryResponse {
  messages: ChatMessageOut[]
  latest_trace?: DebugTrace | null
}

export interface ChatFeedbackRequest {
  session_id: string
  message_id: string
  feedback_type: 'UP' | 'DOWN'
  reason_code?: string
  correction_text?: string
  consent_long_term?: boolean
}

export interface ChatFeedbackResponse {
  feedback_id: string
  applied_session_memory: boolean
  stored_long_term_memory: boolean
}

export interface ChatHandoffRequest {
  session_id: string
  message_id: string
  reason_code: string
  notes?: string
}

export interface ChatHandoffResponse {
  handoff_id: string
  status: string
}

export interface LearningPreferences {
  long_term_personalization_opt_in: boolean
  telemetry_learning_opt_in: boolean
}

export interface LearningPreferencesUpdateRequest {
  long_term_personalization_opt_in?: boolean
  telemetry_learning_opt_in?: boolean
}

export interface OpsDashboardResponse {
  window: {
    days: number
    start_date: string
    end_date: string
  }
  summary: {
    avg_tqs: number
    avg_kgs: number
    rephrase_rate: number
    handoff_rate: number
    refusal_quality: number
    completion_rate: number
  }
  avg_tqs_by_intent: Array<{
    intent: string
    avg_tqs: number
    avg_kgs: number
    turns: number
  }>
  top_kgs_topics: Array<Record<string, unknown>>
  alerts: Record<string, { triggered: boolean; [key: string]: unknown }>
}

export interface ReleaseStatusResponse {
  components: Array<{
    component_key: string
    version_hash: string
    version_label?: string | null
    status: string
    canary_percent: number
    updated_at: string
  }>
  latest_golden_run?: {
    pass_rate: number
    status: string
    created_at: string
  } | null
  latest_canary_run?: {
    canary_percent: number
    rollback_triggered: boolean
    status: string
    updated_at: string
  } | null
}

export interface GoldenRunResponse {
  status: string
  pass_rate: number
  min_required_pass_rate: number
  total_cases: number
  passed_cases: number
  failures: Array<Record<string, unknown>>
}

export interface CanaryStartRequest {
  canary_percent?: number
  experiment_dimension?: string
}

export interface CanaryStartResponse {
  started: boolean
  reason?: string | null
  canary_percent?: number | null
  baseline_metrics?: Record<string, unknown> | null
}

export interface CanaryRollbackRequest {
  notes?: string
}

export interface CanaryRollbackResponse {
  rolled_back: boolean
  status?: string | null
  reason?: string | null
  kgs_delta?: number | null
  handoff_rate?: number | null
  thresholds?: Record<string, unknown> | null
}

export async function getChatHistory(sessionId: string): Promise<ChatHistoryResponse> {
  const res = await fetch(
    `${API_BASE}/api/v1/chat/sessions/${encodeURIComponent(sessionId)}/history`,
    { headers: authHeaders() }
  )
  handleResponse(res)
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `Request failed: ${res.status}`)
  }
  return res.json()
}

export async function postChat(
  message: string,
  sessionId?: string | null,
  language?: string | null
): Promise<ChatResponse> {
  const body: { message: string; session_id?: string; language?: string } = { message }
  if (sessionId != null && sessionId !== '') {
    body.session_id = sessionId
  }
  if (language != null && language !== '') {
    body.language = language
  }
  const res = await fetch(`${API_BASE}/api/v1/chat`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(body),
  })
  handleResponse(res)
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `Request failed: ${res.status}`)
  }
  return res.json()
}

export async function postChatFeedback(body: ChatFeedbackRequest): Promise<ChatFeedbackResponse> {
  const res = await fetch(`${API_BASE}/api/v1/chat/feedback`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(body),
  })
  handleResponse(res)
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `Request failed: ${res.status}`)
  }
  return res.json()
}

export async function postChatHandoff(body: ChatHandoffRequest): Promise<ChatHandoffResponse> {
  const res = await fetch(`${API_BASE}/api/v1/chat/handoff`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(body),
  })
  handleResponse(res)
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `Request failed: ${res.status}`)
  }
  return res.json()
}

export async function getLearningPreferences(): Promise<LearningPreferences> {
  const res = await fetch(`${API_BASE}/api/v1/chat/learning/preferences`, {
    headers: authHeaders(),
  })
  handleResponse(res)
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `Request failed: ${res.status}`)
  }
  return res.json()
}

export async function putLearningPreferences(
  body: LearningPreferencesUpdateRequest
): Promise<LearningPreferences> {
  const res = await fetch(`${API_BASE}/api/v1/chat/learning/preferences`, {
    method: 'PUT',
    headers: authHeaders(),
    body: JSON.stringify(body),
  })
  handleResponse(res)
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `Request failed: ${res.status}`)
  }
  return res.json()
}

export async function getOpsDashboard(days = 7): Promise<OpsDashboardResponse> {
  const res = await fetch(
    `${API_BASE}/api/v1/chat/ops/dashboard?days=${encodeURIComponent(String(days))}`,
    {
      headers: authHeaders(),
    }
  )
  handleResponse(res)
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `Request failed: ${res.status}`)
  }
  return res.json()
}

export async function getReleaseStatus(): Promise<ReleaseStatusResponse> {
  const res = await fetch(`${API_BASE}/api/v1/chat/ops/release/status`, {
    headers: authHeaders(),
  })
  handleResponse(res)
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `Request failed: ${res.status}`)
  }
  return res.json()
}

export async function postReleaseGoldenRun(): Promise<GoldenRunResponse> {
  const res = await fetch(`${API_BASE}/api/v1/chat/ops/release/golden-run`, {
    method: 'POST',
    headers: authHeaders(),
  })
  handleResponse(res)
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `Request failed: ${res.status}`)
  }
  return res.json()
}

export async function postReleaseCanaryStart(
  body: CanaryStartRequest
): Promise<CanaryStartResponse> {
  const res = await fetch(`${API_BASE}/api/v1/chat/ops/release/canary/start`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(body),
  })
  handleResponse(res)
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `Request failed: ${res.status}`)
  }
  return res.json()
}

export async function postReleaseCanaryRollback(
  body: CanaryRollbackRequest
): Promise<CanaryRollbackResponse> {
  const res = await fetch(`${API_BASE}/api/v1/chat/ops/release/canary/rollback`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(body),
  })
  handleResponse(res)
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `Request failed: ${res.status}`)
  }
  return res.json()
}

// Auth API
export interface TokenResponse {
  access_token: string
  token_type: string
  user: {
    id: number
    email: string
    name: string | null
    customer_id?: number | null
    customer?: {
      id: number
      firstname: string
      lastname: string
      email?: string | null
      phoneno?: string | null
    } | null
  }
}

export async function login(email: string, password: string): Promise<TokenResponse> {
  const res = await fetch(`${API_BASE}/api/v1/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail ?? 'Login failed')
  }
  return res.json()
}

export async function signup(
  email: string,
  password: string,
  name?: string | null
): Promise<TokenResponse> {
  const res = await fetch(`${API_BASE}/api/v1/auth/signup`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password, name: name || null }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail ?? 'Signup failed')
  }
  return res.json()
}
