import { useEffect, useState } from 'react'
import { listProfiles, listRuns, type Profile, type Run } from '@/api'
import { Button, Card, PageHeader } from '@/components/ui'
import { fmtDate, fmtSpeed, fmtTime } from '@/lib/format'

const runStatus: Record<Run['status'], { label: string; icon: string; tone: string }> = {
  running: { label: 'En curso', icon: '◌', tone: 'text-st-blue bg-st-blue-soft' },
  completed: { label: 'Completado', icon: '✓', tone: 'text-st-green bg-st-green-soft' },
  failed: { label: 'Fallido', icon: '!', tone: 'text-st-red bg-st-red-soft' },
}

export default function Historial({ onOpen }: { onOpen: (runId: number) => void }) {
  const [runs, setRuns] = useState<Run[] | null>(null)
  const [profiles, setProfiles] = useState<Profile[]>([])
  useEffect(() => { listRuns().then(setRuns, () => setRuns([])); listProfiles().then(setProfiles, () => setProfiles([])) }, [])
  const th = 'px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-ink-3'
  const num = 'px-4 py-3.5 text-right tnum'

  return (
    <div>
      <PageHeader title="Historial" sub="Videos procesados en este equipo." />
      <Card className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="border-b border-line">
            <tr>
              <th className={th}>Fecha</th><th className={th}>Video</th><th className={th}>Escenario</th>
              <th className={`${th} text-right`}>Duración</th><th className={`${th} text-right`}>Velocidad</th>
              <th className={`${th} text-right`}>Vehículos</th><th className={`${th} text-right`}>Confirmadas</th>
              <th className={`${th} text-right`}>Por revisar</th><th className={th}>Estado</th><th className={th}><span className="sr-only">Acciones</span></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {!runs && <tr><td colSpan={10} className="p-4"><div className="h-24 rounded skeleton" /></td></tr>}
            {runs?.map((r) => {
              const st = runStatus[r.status]
              return (
                <tr key={r.id} className="hover:bg-sunken/60">
                  <td className="px-4 py-3.5 whitespace-nowrap text-ink-2">{fmtDate(r.startedAt)}</td>
                  <td className="px-4 py-3.5 font-mono text-xs">{r.video}</td>
                  <td className="px-4 py-3.5">{profiles.find((p) => p.id === r.profile)?.title ?? r.profile}<span className="block text-xs text-ink-3">{r.mode === 'movil' ? 'Cámara en vehículo' : 'Cámara fija'}</span></td>
                  <td className={num}>{r.durationMs ? fmtTime(r.durationMs) : '—'}</td>
                  <td className={`${num} whitespace-nowrap`}>{r.speedFactor ? fmtSpeed(r.speedFactor) : '—'}</td>
                  <td className={num}>{r.vehicles ?? '—'}</td>
                  <td className={num}>{r.confirmed ?? '—'}</td>
                  <td className={num}>{r.unverified ?? '—'}</td>
                  <td className="px-4 py-3.5"><span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ${st.tone}`}><span aria-hidden>{st.icon}</span>{st.label}</span></td>
                  <td className="px-4 py-3.5 text-right"><Button variant="ghost" className="px-3 py-1.5" disabled={!r.vehicles} onClick={() => onOpen(r.id)}>Ver lecturas →</Button></td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </Card>
    </div>
  )
}
