import { useEffect, useRef, useState } from 'react'
import type { Decision, Run, Sighting } from '@/api'
import { ConfidenceBar, Kbd, Plate, StatusBadge } from '@/components/ui'
import { fmtTime, formatPlate, reasonText, vehicleLabel } from '@/lib/format'

interface Props {
  s: Sighting
  run?: Run
  runIndex: number
  editing: boolean
  setEditing: (v: boolean) => void
  onDecide: (d: Decision) => void
  onSkip: () => void
  onView: (v: 'frame' | 'video') => void
}

export default function ReviewPanel({ s, run, runIndex, editing, setEditing, onDecide, onSkip, onView }: Props) {
  const [draft, setDraft] = useState(s.plateText)
  const input = useRef<HTMLInputElement>(null)
  useEffect(() => { setDraft(s.plateText) }, [s.id, s.plateText, editing])
  useEffect(() => { if (editing) input.current?.select() }, [editing])

  const actions: { key: string; icon: string; label: string; tone: string; run: () => void }[] = [
    { key: 'C', icon: '✓', label: 'Es correcta', tone: 'bg-st-green-soft text-st-green hover:ring-st-green', run: () => onDecide({ action: 'confirm' }) },
    { key: 'E', icon: '✎', label: 'Corregir', tone: 'bg-st-blue-soft text-st-blue hover:ring-st-blue', run: () => setEditing(true) },
    { key: 'R', icon: '✗', label: 'No es una placa', tone: 'bg-st-red-soft text-st-red hover:ring-st-red', run: () => onDecide({ action: 'reject' }) },
    { key: 'B', icon: '◐', label: 'Placa borrosa', tone: 'bg-st-gray-soft text-st-gray hover:ring-st-gray', run: () => onDecide({ action: 'illegible' }) },
  ]

  return (
    <div key={s.id} className="anim-in flex flex-col gap-5">
      {s.cropUrl ? (
        <img src={s.cropUrl} alt={`Recorte ampliado de la placa ${s.plateText}`} className="aspect-[3/1] w-full rounded-lg border border-line bg-sunken object-cover" />
      ) : (
        <div className="grid aspect-[3/1] w-full place-items-center rounded-lg border border-line bg-sunken text-sm text-ink-3">Sin recorte</div>
      )}

      <div className="flex flex-col items-center gap-2 py-1">
        {editing ? (
          <form className="w-full" onSubmit={(e) => { e.preventDefault(); if (draft.trim()) onDecide({ action: 'correct', correctedText: draft }) }}>
            <label htmlFor="corr" className="mb-1 block text-xs font-medium text-ink-3">Placa corregida</label>
            <input
              id="corr" ref={input} value={draft} maxLength={7} autoComplete="off" spellCheck={false}
              onChange={(e) => setDraft(e.target.value.toUpperCase().replace(/[^A-Z0-9 ]/g, ''))}
              onKeyDown={(e) => { if (e.key === 'Escape') { e.preventDefault(); setEditing(false) } }}
              className="w-full rounded-md border-[3px] border-black bg-[#f2c200] px-4 py-2 text-center text-4xl font-black uppercase tracking-wider text-black outline-none focus:ring-4 focus:ring-accent"
              style={{ fontFamily: "'Arial Black', Arial, sans-serif" }}
            />
            <p className="mt-2 text-center text-xs text-ink-3"><Kbd>Enter</Kbd> guarda · <Kbd>Esc</Kbd> cancela</p>
          </form>
        ) : (
          <Plate text={s.plateText} size="lg" />
        )}
        {s.ocrText !== s.plateText && <p className="text-sm text-ink-2">El sistema leyó: <span className="font-semibold tnum">{formatPlate(s.ocrText)}</span></p>}
        <StatusBadge status={s.status} />
      </div>

      <div>
        <div className="mb-1 text-xs font-medium text-ink-3">Seguridad del lector</div>
        <ConfidenceBar value={s.confidence} wide />
      </div>

      {s.reasons.length > 0 && (
        <div>
          <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-ink-3">Por qué revisarla</h3>
          <ul className="space-y-1.5 text-sm">
            {s.reasons.map((r) => (
              <li key={r} className="flex gap-2"><span aria-hidden className="text-st-amber">•</span>{reasonText[r] ?? r}</li>
            ))}
          </ul>
        </div>
      )}

      <p className="text-sm text-ink-2 tnum">
        {vehicleLabel[s.vehicleType]} · aparece en {fmtTime(s.firstSeenMs)}–{fmtTime(s.lastSeenMs)} · video {runIndex}
        {run && <span className="block truncate font-mono text-xs text-ink-3">{run.video}</span>}
      </p>

      <div className="grid grid-cols-2 gap-2">
        <button onClick={() => onView('video')} disabled={editing} className="flex items-center justify-between gap-2 rounded-lg border border-line px-3 py-2.5 text-sm font-medium transition hover:bg-sunken disabled:opacity-40">
          <span><span aria-hidden className="mr-1.5">▶</span>Ir al video <span className="text-ink-3 tnum">{fmtTime(s.firstSeenMs)}</span></span><Kbd>V</Kbd>
        </button>
        <button onClick={() => onView('frame')} disabled={editing} className="flex items-center justify-between gap-2 rounded-lg border border-line px-3 py-2.5 text-sm font-medium transition hover:bg-sunken disabled:opacity-40">
          <span><span aria-hidden className="mr-1.5">▣</span>Captura completa</span><Kbd>F</Kbd>
        </button>
      </div>

      <div className="grid grid-cols-2 gap-2">
        {actions.map((a) => (
          <button key={a.key} onClick={a.run} disabled={editing}
            className={`flex items-center justify-between gap-2 rounded-lg px-4 py-3 text-sm font-semibold ring-1 ring-transparent transition disabled:opacity-40 ${a.tone}`}>
            <span><span aria-hidden className="mr-2">{a.icon}</span>{a.label}</span>
            <Kbd>{a.key}</Kbd>
          </button>
        ))}
        <button onClick={onSkip} disabled={editing} className="col-span-2 flex items-center justify-between rounded-lg border border-line px-4 py-2.5 text-sm font-medium text-ink-2 transition hover:bg-sunken disabled:opacity-40">
          <span>Saltar</span><Kbd>S</Kbd>
        </button>
      </div>
      <p className="text-center text-xs text-ink-3">Usa las flechas para moverte por la cuadrícula.</p>
    </div>
  )
}
