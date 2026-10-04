import type { Sighting } from '@/api'
import { ConfidenceBar, Plate, StatusBadge } from '@/components/ui'
import { vehicleLabel } from '@/lib/format'

export default function SightingCard({ s, selected, onSelect }: { s: Sighting; selected: boolean; onSelect: () => void }) {
  return (
    <button
      data-id={s.id}
      onClick={onSelect}
      aria-pressed={selected}
      className={`group flex flex-col overflow-hidden rounded-xl border bg-surface text-left shadow-soft transition ${selected ? 'border-accent ring-2 ring-accent' : 'border-line hover:-translate-y-0.5 hover:border-ink-3'}`}
    >
      {s.cropUrl ? (
        <img src={s.cropUrl} alt={`Recorte de la placa ${s.plateText}`} className="aspect-[3/1] w-full bg-sunken object-cover" />
      ) : (
        <div className="grid aspect-[3/1] w-full place-items-center bg-sunken text-sm text-ink-3">Sin recorte</div>
      )}
      <div className="flex flex-1 flex-col gap-3 p-3.5">
        <div className="flex items-center justify-between gap-2">
          <Plate text={s.plateText} size="sm" />
          <span className="text-xs text-ink-3">{vehicleLabel[s.vehicleType]}</span>
        </div>
        <div className="mt-auto flex items-center justify-between gap-2">
          <ConfidenceBar value={s.confidence} />
          <StatusBadge status={s.status} />
        </div>
      </div>
    </button>
  )
}

export function SightingCardSkeleton() {
  return (
    <div className="overflow-hidden rounded-xl border border-line bg-surface" aria-hidden>
      <div className="aspect-[3/1] skeleton" />
      <div className="space-y-3 p-3.5">
        <div className="h-6 w-24 rounded skeleton" />
        <div className="h-4 w-full rounded skeleton" />
      </div>
    </div>
  )
}
