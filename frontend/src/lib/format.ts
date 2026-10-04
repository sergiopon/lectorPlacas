import type { SightingStatus, VehicleType } from '@/api'

export const formatPlate = (t: string) => (t.length >= 4 ? `${t.slice(0, 3)} ${t.slice(3)}` : t)

export const fmtTime = (ms: number) => {
  const s = Math.floor(ms / 1000)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const ss = String(s % 60).padStart(2, '0')
  return h ? `${h}:${String(m).padStart(2, '0')}:${ss}` : `${m}:${ss}`
}

export const fmtBytes = (b: number) => (b >= 1e9 ? `${(b / 1e9).toLocaleString('es-CO', { maximumFractionDigits: 1 })} GB` : `${Math.round(b / 1e6)} MB`)
export const fmtPct = (v: number, d = 0) => `${(v * 100).toLocaleString('es-CO', { maximumFractionDigits: d, minimumFractionDigits: d })} %`
export const fmtSpeed = (v: number) => `${v.toLocaleString('es-CO', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}x tiempo real`
export const fmtDate = (iso: string) => new Date(iso).toLocaleString('es-CO', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })

export const vehicleLabel: Record<VehicleType, string> = { car: 'Carro', motorcycle: 'Moto', bus: 'Bus', truck: 'Camión' }

export const statusMeta: Record<SightingStatus, { label: string; icon: string; tone: string }> = {
  unverified: { label: 'Por revisar', icon: '◷', tone: 'text-st-amber bg-st-amber-soft' },
  confirmed: { label: 'Confirmada', icon: '✓', tone: 'text-st-green bg-st-green-soft' },
  corrected: { label: 'Corregida', icon: '✎', tone: 'text-st-blue bg-st-blue-soft' },
  rejected: { label: 'Descartada', icon: '✗', tone: 'text-st-red bg-st-red-soft' },
  illegible: { label: 'Borrosa', icon: '◐', tone: 'text-st-gray bg-st-gray-soft' },
}

export const reasonText: Record<string, string> = {
  insufficient_readings: 'Se leyó pocas veces',
  low_confidence: 'El lector no estaba seguro',
  low_agreement: 'Las lecturas no coinciden entre sí',
  unrecognized_format: 'No parece una placa colombiana',
  unverified_format: 'Formato de placa poco común',
  vehicle_format_mismatch: 'El formato no corresponde al tipo de vehículo',
  ambiguous_format: 'Encaja en más de un formato',
  predicted_illegible: 'Parece borrosa (filtro automático)',
  predicted_not_plate: 'Parece que no es una placa (filtro automático)',
  correction_conflict: 'Podría ser otra placa: una letra o un número dudoso',
}

export const isTyping = (el: EventTarget | null) =>
  el instanceof HTMLElement && (el.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName))
