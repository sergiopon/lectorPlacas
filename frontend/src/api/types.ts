export type VehicleType = 'car' | 'motorcycle' | 'bus' | 'truck'
export type SightingStatus = 'unverified' | 'confirmed' | 'corrected' | 'rejected' | 'illegible'

export interface Sighting {
  id: number
  runId: number
  vehicleType: VehicleType
  plateText: string
  ocrText: string
  confidence: number
  agreement: number
  numReadings: number
  status: SightingStatus
  reasons: string[]
  hiddenLowQuality: boolean
  duplicates: number
  firstSeenMs: number
  lastSeenMs: number
  cropUrl: string | null
  duplicateOf: number | null
  reviewedAt: string | null
}

export interface Run {
  id: number
  video: string
  profile: string
  mode: 'estatico' | 'movil' | null
  startedAt: string
  durationMs: number | null
  speedFactor: number | null
  vehicles: number | null
  confirmed: number | null
  unverified: number | null
  status: 'running' | 'completed' | 'failed'
}

export interface Decision {
  action: 'confirm' | 'correct' | 'reject' | 'illegible'
  correctedText?: string
}

export interface Video { name: string; path: string; durationMs: number | null; sizeBytes: number }

export interface Profile {
  id: string
  mode: 'estatico' | 'movil'
  title: string
  description: string
  isDefault: boolean
}

export type SightingTab = SightingStatus | 'all' | 'hidden'

export interface SightingFilters { tab: SightingTab; query?: string; runId?: number | null }

export interface SightingList { items: Sighting[]; total: number; counts: Record<SightingTab, number> }

export type RunEvent =
  | { type: 'progress'; fraction: number | null; processedMs: number; durationMs: number | null; plates: number; speedFactor: number | null }
  | { type: 'done'; summary: RunSummary }
  | { type: 'cancelled' }
  | { type: 'failed'; message: string }

export interface RunSummary {
  runId: number
  legible: number
  unverified: number
  hiddenLowQuality: number
  autoConfirmed: number
  durationMs: number
}

export interface StartedJob { jobId: string; durationMs: number | null }

export interface Stat { value: number | null; sub: string }

export interface RunMetrics {
  runId: number
  video: string
  legible: number
  illegible: number
  rejected: number
  accuracy: number | null
  cer: number | null
}

export interface Metrics {
  auditedAccuracy: Stat
  fullPlateReads: Stat
  charErrorRate: Stat
  autoConfirmRate: Stat
  perVideo: RunMetrics[]
}

export interface Settings { cropRetentionDays: number; logRetentionDays: number }

/** Fotograma completo del momento en que aparece la placa. */
export interface SightingFrame {
  frameUrl: string
  timestampMs: number
}

export interface VideoSource { url: string; name: string }

export interface PurgeResult { crops: number; sightings: number; runs: number; exports: number }
