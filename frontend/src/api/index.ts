// Módulo único de datos: cliente de la API real de lector-web (specs 066, 067 y 076).
import { ApiError, getJson, postJson, qs } from './http'
import type {
  Decision,
  Metrics,
  Profile,
  PurgeResult,
  Run,
  RunEvent,
  RunMetrics,
  Settings,
  Sighting,
  SightingFilters,
  SightingFrame,
  SightingList,
  SightingStatus,
  SightingTab,
  StartedJob,
  Stat,
  Video,
  VideoSource,
} from './types'

export * from './types'
export { ApiError } from './http'

const listeners = new Set<() => void>()
const changed = () => listeners.forEach((f) => f())

/** Notifica cuando cambian los datos (p. ej. tras una decisión). */
export function onDataChange(fn: () => void) {
  listeners.add(fn)
  return () => void listeners.delete(fn)
}

interface ProfileOut { name: string; label: string; description: string; mode: 'estatico' | 'movil'; default: boolean }
interface RunPage { items: Run[]; page: number; pageSize: number }
interface SightingPage { items: Sighting[]; total: number; page: number; pageSize: number }
interface JobOut {
  jobId: string
  state: 'running' | 'completed' | 'cancelled' | 'failed'
  runId: number | null
  durationMs: number | null
  positionMs: number | null
  sightingsSaved: number | null
  fraction: number | null
  message: string | null
}
interface MetricsOut {
  confirmedTotal: number
  confirmedAudited: number
  confirmedKept: number
  precisionConfirmed: number | null
  unverifiedTotal: number
  reviewedReadings: number
  cer: number | null
  exactMatchRate: number | null
}
interface RunMetricsOut { runId: number; legible: number; illegible: number; rejected: number; precision: number | null; cer: number | null }
interface SettingsOut { cropsDays: number; recordsDays: number; trainingDays: number }
interface PurgeOut { cropsDeleted: number; sightingsDeleted: number; runsDeleted: number; exportsDeleted: number }

const RUNS_PAGE_SIZE = 50

export async function listVideos(): Promise<Video[]> {
  return getJson<Video[]>('/api/videos')
}

export async function listProfiles(): Promise<Profile[]> {
  const items = await getJson<ProfileOut[]>('/api/profiles')
  return items.map((p) => ({ id: p.name, title: p.label, description: p.description, mode: p.mode, isDefault: p.default }))
}

export async function listRuns(): Promise<Run[]> {
  const all: Run[] = []
  for (let page = 1; ; page++) {
    const res = await getJson<RunPage>('/api/runs' + qs({ page }))
    all.push(...res.items)
    if (res.items.length < RUNS_PAGE_SIZE) break
  }
  return all.sort((a, b) => b.startedAt.localeCompare(a.startedAt))
}

export async function listSightings(f: SightingFilters, page = 1): Promise<SightingList> {
  const q = (f.query ?? '').toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 10)
  const base = { q, run: f.runId }
  const filter =
    f.tab === 'hidden'
      ? { hidden: true }
      : f.tab === 'all'
        ? { hidden: false }
        : { status: f.tab, hidden: false }
  const [list, counts] = await Promise.all([
    getJson<SightingPage>('/api/sightings' + qs({ ...base, ...filter, page })),
    getJson<Record<SightingTab, number>>('/api/sighting-counts' + qs(base)),
  ])
  return { items: list.items, total: list.total, counts }
}

export async function getSighting(id: number): Promise<Sighting | null> {
  try {
    return await getJson<Sighting>('/api/sightings/' + id)
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return null
    throw e
  }
}

export async function getPendingCount(): Promise<number> {
  const res = await getJson<{ pending: number }>('/api/summary')
  return res.pending
}

export async function decide(id: number, d: Decision): Promise<Sighting> {
  const body = d.action === 'correct' ? { action: d.action, correctedText: d.correctedText } : { action: d.action }
  const res = await postJson<Sighting>('/api/sightings/' + id + '/decision', body)
  changed()
  return res
}

export async function startRun(video: Video, profile: string): Promise<StartedJob> {
  const job = await postJson<JobOut>('/api/jobs', { video: video.path, profile })
  return { jobId: job.jobId, durationMs: video.durationMs }
}

async function summarize(job: JobOut): Promise<RunEvent> {
  const runId = job.runId ?? 0
  const [counts, page] = await Promise.all([
    getJson<Record<SightingTab, number>>('/api/sighting-counts' + qs({ run: runId })),
    getJson<RunPage>('/api/runs' + qs({ page: 1 })),
  ])
  const run = page.items.find((r) => r.id === runId)
  changed()
  return {
    type: 'done',
    summary: {
      runId,
      legible: counts.unverified + counts.confirmed,
      unverified: counts.unverified,
      hiddenLowQuality: counts.hidden,
      autoConfirmed: counts.confirmed,
      durationMs: run?.durationMs ?? 0,
    },
  }
}

export function subscribeRunProgress(jobId: string, onEvent: (e: RunEvent) => void): () => void {
  const source = new EventSource('/api/jobs/' + jobId + '/events')
  const start = Date.now()
  source.addEventListener('progress', (ev) => {
    const job = JSON.parse((ev as MessageEvent<string>).data) as JobOut
    const processedMs = job.positionMs ?? 0
    const elapsed = Date.now() - start
    onEvent({
      type: 'progress',
      fraction: job.fraction,
      processedMs,
      durationMs: job.durationMs,
      plates: job.sightingsSaved ?? 0,
      speedFactor: elapsed > 1000 ? processedMs / elapsed : null,
    })
  })
  source.addEventListener('done', (ev) => {
    source.close()
    const job = JSON.parse((ev as MessageEvent<string>).data) as JobOut
    if (job.state === 'completed') {
      summarize(job).then(onEvent, () => onEvent({ type: 'failed', message: 'Error al procesar' }))
    } else if (job.state === 'cancelled') {
      onEvent({ type: 'cancelled' })
    } else {
      onEvent({ type: 'failed', message: job.message ?? 'Error al procesar' })
    }
  })
  source.onerror = () => {
    source.close()
    onEvent({ type: 'failed', message: 'Se perdió la conexión con el servidor' })
  }
  return () => source.close()
}

export async function cancelRun(jobId: string): Promise<void> {
  await postJson<JobOut>('/api/jobs/' + jobId + '/cancel')
}

const NO_DATA: Stat = { value: null, sub: 'Sin datos todavía' }

export async function getMetrics(): Promise<Metrics> {
  const [m, byRun, runs] = await Promise.all([
    getJson<MetricsOut>('/api/metrics').catch((e: unknown) => {
      if (e instanceof ApiError && e.status === 404) return null
      throw e
    }),
    getJson<RunMetricsOut[]>('/api/metrics/runs'),
    listRuns(),
  ])
  if (!m) return { auditedAccuracy: NO_DATA, fullPlateReads: NO_DATA, charErrorRate: NO_DATA, autoConfirmRate: NO_DATA, perVideo: [] }
  const total = m.confirmedTotal + m.unverifiedTotal
  const reviewed = m.reviewedReadings + ' lecturas revisadas'
  const perVideo: RunMetrics[] = byRun.map((r) => ({
    runId: r.runId,
    video: runs.find((x) => x.id === r.runId)?.video ?? 'Video ' + r.runId,
    legible: r.legible,
    illegible: r.illegible,
    rejected: r.rejected,
    accuracy: r.precision,
    cer: r.cer,
  }))
  return {
    auditedAccuracy: { value: m.precisionConfirmed, sub: m.confirmedKept + ' de ' + m.confirmedAudited },
    fullPlateReads: { value: m.exactMatchRate, sub: reviewed },
    charErrorRate: { value: m.cer, sub: reviewed },
    autoConfirmRate: { value: total > 0 ? m.confirmedTotal / total : null, sub: m.confirmedTotal + ' de ' + total },
    perVideo,
  }
}

export async function getSettings(): Promise<Settings> {
  const s = await getJson<SettingsOut>('/api/settings')
  return { cropRetentionDays: s.cropsDays, logRetentionDays: s.recordsDays }
}

/** Exporta el CSV a `data/exports/` y devuelve el nombre del archivo. No descarga nada (SEG-08). */
export async function exportCsv(status: SightingStatus | 'all'): Promise<string> {
  const res = await postJson<{ file: string }>('/api/export', { status: status === 'all' ? null : status })
  return res.file
}

export async function purgeExpired(): Promise<PurgeResult> {
  const r = await postJson<PurgeOut>('/api/purge')
  changed()
  return { crops: r.cropsDeleted, sightings: r.sightingsDeleted, runs: r.runsDeleted, exports: r.exportsDeleted }
}

/** Fotograma completo del momento en que aparece la placa. */
export function getSightingFrame(s: Sighting): SightingFrame {
  return { frameUrl: '/api/sightings/' + s.id + '/frame', timestampMs: Math.floor((s.firstSeenMs + s.lastSeenMs) / 2) }
}

/** URL reproducible del video original de la corrida. */
export function getVideoSource(runId: number, name: string): VideoSource {
  return { url: '/api/runs/' + runId + '/video', name }
}
