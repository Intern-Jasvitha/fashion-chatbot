import { Bot, Clock3, Route, Search } from 'lucide-react'
import { memo, useEffect, useMemo, useRef } from 'react'

import { Button } from '@/components/ui/button'
import type {
  CanaryRollbackResponse,
  CanaryStartResponse,
  DebugTrace,
  GoldenRunResponse,
  LearningPreferences,
  OpsDashboardResponse,
  ReleaseStatusResponse,
  TraceStep,
} from '@/lib/api'

interface AgentDebugPanelProps {
  trace: DebugTrace | null
  learningPreferences?: LearningPreferences | null
  opsDashboard?: OpsDashboardResponse | null
  releaseStatus?: ReleaseStatusResponse | null
  latestGoldenRun?: GoldenRunResponse | null
  latestCanaryStart?: CanaryStartResponse | null
  latestCanaryRollback?: CanaryRollbackResponse | null
  onRunGoldenGate?: () => void | Promise<void>
  onStartCanary?: () => void | Promise<void>
  onRollbackCanary?: () => void | Promise<void>
  isRunningGoldenGate?: boolean
  isStartingCanary?: boolean
  isRollingBackCanary?: boolean
}

function prettifyKey(key: string): string {
  return key
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

function formatValue(value: unknown): string {
  if (value == null) return '-'
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

function statusClass(status: string): string {
  if (status === 'ok') return 'debug-status-ok'
  if (status === 'error') return 'debug-status-error'
  return 'debug-status-info'
}

function asRecord(value: unknown): Record<string, unknown> {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return value as Record<string, unknown>
  }
  return {}
}

const TraceDetailRows = memo(function TraceDetailRows({ step }: { step: TraceStep }) {
  const detailEntries = useMemo(
    () =>
      Object.entries(step.details ?? {}).filter(([, value]) => value !== undefined && value !== null && value !== ''),
    [step.details]
  )

  if (detailEntries.length === 0) {
    return null
  }

  return (
    <div className="mt-2 space-y-1.5">
      {detailEntries.map(([key, value]) => (
        <div key={key} className="text-[12px] leading-relaxed text-muted-foreground">
          <span className="font-medium text-foreground/80">{prettifyKey(key)}:</span> {formatValue(value)}
        </div>
      ))}
    </div>
  )
})

export const AgentDebugPanel = memo(function AgentDebugPanel({
  trace,
  learningPreferences,
  opsDashboard,
  releaseStatus,
  latestGoldenRun,
  latestCanaryStart,
  latestCanaryRollback,
  onRunGoldenGate,
  onStartCanary,
  onRollbackCanary,
  isRunningGoldenGate = false,
  isStartingCanary = false,
  isRollingBackCanary = false,
}: AgentDebugPanelProps) {
  const scrollRef = useRef<HTMLDivElement>(null)

  // Keep newest request visible from the top whenever trace changes.
  useEffect(() => {
    if (!scrollRef.current) return
    scrollRef.current.scrollTo({ top: 0, behavior: 'smooth' })
  }, [trace?.request_id])

  const orderedSteps = useMemo(() => [...(trace?.steps ?? [])].reverse(), [trace?.steps])
  const learningGuardrailsStep = useMemo(
    () => (trace?.steps ?? []).find((step) => step.step === 'learning_guardrails'),
    [trace?.steps]
  )
  const learningGuardrailDetails = useMemo(
    () => asRecord(learningGuardrailsStep?.details),
    [learningGuardrailsStep?.details]
  )

  return (
    <aside className="hidden xl:flex w-[22rem] border-l border-border/80 bg-card/55 backdrop-blur-sm flex-col min-h-0">
      <div className="px-4 py-3 border-b border-border/70">
        <div className="flex items-center gap-2 text-foreground">
          <Search className="w-4 h-4" />
          <h2 className="text-sm font-semibold tracking-tight">Execution Trace</h2>
        </div>
        <p className="text-[11px] text-muted-foreground mt-1">Latest turn debug timeline</p>
      </div>

      {!trace ? (
        <div className="p-4 text-sm text-muted-foreground leading-relaxed">
          No trace yet. Send a message to inspect routing and agent execution.
        </div>
      ) : (
        <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-4">
          <div className="rounded-lg border border-border/70 bg-background/60 p-3">
            <div className="text-[11px] text-muted-foreground uppercase tracking-wider">Latest Message Trace</div>
            <div className="mt-1 text-[11px] text-muted-foreground uppercase tracking-wider">Request ID</div>
            <div className="mt-0.5 text-xs text-foreground break-all">{trace.request_id}</div>
            <div className="mt-2 text-[11px] text-muted-foreground uppercase tracking-wider">User Message</div>
            <div className="debug-query-highlight mt-1">
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground">This trace belongs to query</div>
              <div className="mt-1 text-sm font-medium text-foreground break-words">{trace.user_query}</div>
            </div>
          </div>

          <div className="rounded-lg border border-border/70 bg-background/60 p-3 space-y-2">
            <div className="flex items-center gap-2 text-xs text-foreground">
              <Route className="w-3.5 h-3.5" />
              <span className="font-medium">Intent</span>
              <span className="ml-auto px-2 py-0.5 rounded-full bg-secondary text-secondary-foreground text-[11px]">
                {(trace.intent || 'unknown').toUpperCase()}
              </span>
            </div>
            <div className="flex items-start gap-2 text-xs text-muted-foreground">
              <Bot className="w-3.5 h-3.5 mt-0.5" />
              <div className="flex flex-wrap gap-1.5">
                {(trace.called_agents || []).length ? (
                  trace.called_agents.map((agent) => (
                    <span key={agent} className="px-2 py-0.5 rounded-full border border-border/80 bg-card text-foreground/90 text-[11px]">
                      {agent}
                    </span>
                  ))
                ) : (
                  <span>None</span>
                )}
              </div>
            </div>
          </div>

          <div className="rounded-lg border border-border/70 bg-background/60 p-3 space-y-2">
            <div className="text-[11px] text-muted-foreground uppercase tracking-wider">Governance</div>
            <div className="text-xs text-foreground">
              Learning Allowed: {String(Boolean(learningGuardrailDetails.learning_allowed))}
            </div>
            <div className="text-xs text-muted-foreground">
              Exclusion: {String(learningGuardrailDetails.exclusion_reason_code ?? '-')}
            </div>
            <div className="text-xs text-muted-foreground">
              Long-Term Personalization: {String(Boolean(learningPreferences?.long_term_personalization_opt_in))}
            </div>
            <div className="text-xs text-muted-foreground">
              Telemetry Learning: {String(Boolean(learningPreferences?.telemetry_learning_opt_in ?? true))}
            </div>
          </div>

          <div className="rounded-lg border border-border/70 bg-background/60 p-3 space-y-2">
            <div className="text-[11px] text-muted-foreground uppercase tracking-wider">Release Controls</div>
            <div className="text-xs text-muted-foreground">
              Golden Gate: {latestGoldenRun?.status ?? releaseStatus?.latest_golden_run?.status ?? '-'} /{' '}
              {latestGoldenRun?.pass_rate ?? releaseStatus?.latest_golden_run?.pass_rate ?? '-'}
            </div>
            <div className="text-xs text-muted-foreground">
              Canary: {latestCanaryRollback?.status ?? releaseStatus?.latest_canary_run?.status ?? '-'} /{' '}
              {releaseStatus?.latest_canary_run?.canary_percent ?? latestCanaryStart?.canary_percent ?? 0}%
            </div>
            <div className="space-y-1.5">
              {(releaseStatus?.components ?? []).map((component) => (
                <div key={component.component_key} className="text-[11px] text-muted-foreground break-all">
                  {component.component_key}: {component.version_hash.slice(0, 10)}... ({component.status})
                </div>
              ))}
            </div>
            <div className="flex flex-col gap-1.5 pt-1">
              <Button size="sm" variant="secondary" onClick={onRunGoldenGate} disabled={isRunningGoldenGate}>
                {isRunningGoldenGate ? 'Running Golden...' : 'Run Golden Gate'}
              </Button>
              <Button size="sm" variant="secondary" onClick={onStartCanary} disabled={isStartingCanary}>
                {isStartingCanary ? 'Starting Canary...' : 'Start Canary'}
              </Button>
              <Button size="sm" variant="secondary" onClick={onRollbackCanary} disabled={isRollingBackCanary}>
                {isRollingBackCanary ? 'Evaluating Rollback...' : 'Rollback Check'}
              </Button>
            </div>
          </div>

          <div className="rounded-lg border border-border/70 bg-background/60 p-3 space-y-2">
            <div className="text-[11px] text-muted-foreground uppercase tracking-wider">Ops KPI</div>
            <div className="text-xs text-muted-foreground">Avg TQS: {opsDashboard?.summary?.avg_tqs ?? '-'}</div>
            <div className="text-xs text-muted-foreground">Avg KGS: {opsDashboard?.summary?.avg_kgs ?? '-'}</div>
            <div className="text-xs text-muted-foreground">Handoff Rate: {opsDashboard?.summary?.handoff_rate ?? '-'}</div>
            <div className="text-xs text-muted-foreground">
              Alerts:{' '}
              {Object.entries(opsDashboard?.alerts ?? {})
                .filter(([, value]) => value?.triggered)
                .map(([key]) => key)
                .join(', ') || 'none'}
            </div>
          </div>

          <div className="space-y-3">
            {orderedSteps.map((step, index) => (
              <div key={`${step.agent}-${step.step}-${index}`} className="trace-step-card">
                <div className="flex items-start gap-2">
                  <span className={`trace-step-dot ${statusClass(step.status)}`} aria-hidden />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-medium text-foreground">{prettifyKey(step.step)}</span>
                      <span className="text-[10px] px-1.5 py-0.5 rounded border border-border/70 text-muted-foreground">
                        {step.agent}
                      </span>
                      <span className={`text-[10px] px-1.5 py-0.5 rounded-full ml-auto ${statusClass(step.status)}`}>
                        {step.status}
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground leading-relaxed">{step.summary}</p>
                    {typeof step.duration_ms === 'number' && (
                      <div className="mt-1 text-[11px] text-muted-foreground flex items-center gap-1">
                        <Clock3 className="w-3 h-3" />
                        {step.duration_ms} ms
                      </div>
                    )}
                    <TraceDetailRows step={step} />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </aside>
  )
})
