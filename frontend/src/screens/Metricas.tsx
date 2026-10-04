import { useEffect, useState } from 'react'
import { getMetrics, type Metrics } from '@/api'
import { Card, PageHeader, Stat } from '@/components/ui'
import { fmtPct } from '@/lib/format'

const noData = { value: null, sub: 'Sin datos todavía' }
const emptyMetrics: Metrics = { auditedAccuracy: noData, fullPlateReads: noData, charErrorRate: noData, autoConfirmRate: noData, perVideo: [] }

export default function Metricas() {
  const [m, setM] = useState<Metrics | null>(null)
  useEffect(() => { getMetrics().then(setM, () => setM(emptyMetrics)) }, [])

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader title="Métricas" sub="Estimación a partir de la revisión humana." />
      {!m ? (
        <div className="grid grid-cols-4 gap-4">{[0, 1, 2, 3].map((i) => <div key={i} className="h-32 rounded-xl skeleton" />)}</div>
      ) : (
        <>
          <div className="grid grid-cols-4 gap-4 max-[1000px]:grid-cols-2">
            <Stat label="Precisión de confirmadas auditadas" value={pct(m.auditedAccuracy.value)} sub={m.auditedAccuracy.sub} />
            <Stat label="Placas leídas completas" value={pct(m.fullPlateReads.value)} sub={m.fullPlateReads.sub} />
            <Stat label="Error por carácter" value={pct(m.charErrorRate.value)} sub={m.charErrorRate.sub} />
            <Stat label="Confirmación automática" value={pct(m.autoConfirmRate.value)} sub={m.autoConfirmRate.sub} />
          </div>
          {m.perVideo.length === 0 ? (
            <p className="mt-6 text-sm text-ink-2">Aún no hay lecturas revisadas por video.</p>
          ) : (
            <div className="mt-6 grid grid-cols-[3fr_2fr] gap-4 max-[1000px]:grid-cols-1">
              <Card className="p-6"><h2 className="mb-1 font-semibold">Resultado por video</h2><StackedBars data={m.perVideo} /></Card>
              <Card className="p-6"><h2 className="mb-1 font-semibold">Evolución a lo largo de los videos</h2><Lines data={m.perVideo} /></Card>
            </div>
          )}
          <p className="mt-4 text-xs text-ink-3">Estimación a partir de la revisión humana.</p>
        </>
      )}
    </div>
  )
}

const pct = (v: number | null) => (v === null ? '—' : fmtPct(v, 1))

type Row = Metrics['perVideo'][number]
const series = [
  { key: 'legible', label: 'Legibles', color: 'var(--accent)' },
  { key: 'illegible', label: 'Borrosas', color: 'var(--st-gray)' },
  { key: 'rejected', label: 'No es placa', color: 'var(--st-red)' },
] as const

function Legend({ items }: { items: { label: string; color: string; dash?: boolean }[] }) {
  return (
    <ul className="mb-4 flex flex-wrap gap-4 text-xs text-ink-2">
      {items.map((i) => (
        <li key={i.label} className="flex items-center gap-1.5">
          <span aria-hidden className="h-2.5 w-2.5 rounded-sm" style={{ background: i.color }} />{i.label}
        </li>
      ))}
    </ul>
  )
}

function StackedBars({ data }: { data: Row[] }) {
  const max = Math.max(...data.map((d) => d.legible + d.illegible + d.rejected))
  const W = 560, H = 240, pad = 28, bw = 46
  const step = (W - pad) / data.length
  return (
    <>
      <Legend items={series.map((s) => ({ label: s.label, color: s.color }))} />
      <svg viewBox={`0 0 ${W} ${H + 40}`} className="w-full" role="img" aria-label="Barras apiladas de legibles, borrosas y no es placa por video">
        {[0, 0.5, 1].map((t) => (
          <g key={t}>
            <line x1={pad} x2={W} y1={H - t * (H - 10)} y2={H - t * (H - 10)} stroke="var(--line)" />
            <text x={pad - 6} y={H - t * (H - 10) + 4} textAnchor="end" fontSize="10" fill="var(--ink-3)">{Math.round(t * max)}</text>
          </g>
        ))}
        {data.map((d, i) => {
          let y = H
          const x = pad + i * step + (step - bw) / 2
          return (
            <g key={d.video}>
              <title>{`${d.video}: ${d.legible} legibles, ${d.illegible} borrosas, ${d.rejected} no es placa`}</title>
              {series.map((s) => {
                const h = (d[s.key] / max) * (H - 10)
                y -= h
                return <rect key={s.key} x={x} y={y} width={bw} height={Math.max(0, h - 1.5)} rx="2" fill={s.color} />
              })}
              <text x={x + bw / 2} y={H + 16} textAnchor="middle" fontSize="10" fill="var(--ink-2)">Video {i + 1}</text>
              <text x={x + bw / 2} y={H + 30} textAnchor="middle" fontSize="9" fill="var(--ink-3)">{d.legible + d.illegible + d.rejected}</text>
            </g>
          )
        })}
      </svg>
    </>
  )
}

function Lines({ data }: { data: Row[] }) {
  const W = 400, h = 100, pad = 34
  const x = (i: number) => pad + (i * (W - pad - 12)) / Math.max(1, data.length - 1)
  const panel = (raw: (number | null)[], lo: number, hi: number, color: string, label: string, top: number) => {
    const y = (v: number) => top + h - ((v - lo) / (hi - lo)) * h
    const pts = raw.flatMap((v, i) => (v === null ? [] : [{ v, i }]))
    return (
      <g>
        <text x={pad} y={top - 8} fontSize="11" fontWeight="600" fill="var(--ink-2)">{label}</text>
        {[lo, hi].map((t) => (
          <g key={t}><line x1={pad} x2={W - 12} y1={y(t)} y2={y(t)} stroke="var(--line)" /><text x={pad - 6} y={y(t) + 4} textAnchor="end" fontSize="10" fill="var(--ink-3)">{Math.round(t * 100)}%</text></g>
        ))}
        {pts.length >= 2 && <polyline points={pts.map((p) => `${x(p.i)},${y(p.v)}`).join(' ')} fill="none" stroke={color} strokeWidth="2.25" strokeLinejoin="round" />}
        {pts.map(({ v, i }) => <circle key={i} cx={x(i)} cy={y(v)} r="3.5" fill="var(--surface)" stroke={color} strokeWidth="2"><title>{`Video ${i + 1}: ${fmtPct(v, 1)}`}</title></circle>)}
      </g>
    )
  }
  return (
    <>
      <Legend items={[{ label: 'Precisión', color: 'var(--accent)' }, { label: 'Error por carácter', color: 'var(--st-amber)' }]} />
      <svg viewBox={`0 0 ${W} 300`} className="w-full" role="img" aria-label="Precisión y error por carácter a lo largo de los videos">
        {panel(data.map((d) => d.accuracy), 0.8, 1, 'var(--accent)', 'Precisión', 20)}
        {panel(data.map((d) => d.cer), 0, 0.08, 'var(--st-amber)', 'Error por carácter', 160)}
        {data.map((_, i) => <text key={i} x={x(i)} y={292} textAnchor="middle" fontSize="10" fill="var(--ink-2)">V{i + 1}</text>)}
      </svg>
    </>
  )
}
