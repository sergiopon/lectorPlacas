import { useEffect, useRef, useState } from 'react'
import { exportCsv, getSettings, purgeExpired, type Settings, type SightingStatus } from '@/api'
import { Button, Card, PageHeader } from '@/components/ui'
import { statusMeta } from '@/lib/format'

export default function Ajustes() {
  const [s, setS] = useState<Settings | null>(null)
  const [csvStatus, setCsvStatus] = useState<SightingStatus | 'all'>('all')
  const [msg, setMsg] = useState('')
  const [exported, setExported] = useState('')
  const [busy, setBusy] = useState(false)
  const dialog = useRef<HTMLDialogElement>(null)
  useEffect(() => { getSettings().then(setS, () => setS(null)) }, [])

  const download = async () => {
    try {
      const file = await exportCsv(csvStatus)
      setExported(`Exportado a data/exports/${file}`)
    } catch (e) {
      setExported(e instanceof Error ? e.message : 'No se pudo exportar')
    }
  }

  const purge = async () => {
    setBusy(true)
    try {
      const r = await purgeExpired()
      setMsg(`Purga completada: ${r.crops} recortes, ${r.sightings} lecturas, ${r.runs} corridas y ${r.exports} exportaciones eliminados.`)
    } catch (e) {
      setMsg(e instanceof Error ? e.message : 'No se pudo purgar')
    }
    setBusy(false)
    dialog.current?.close()
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <PageHeader title="Ajustes" />
      <Card className="p-6">
        <h2 className="font-semibold">Retención de datos</h2>
        <p className="mt-1 text-sm text-ink-2">Pasado este plazo, los datos se pueden purgar. Los recortes son las imágenes de cada placa; los registros guardan lecturas y decisiones.</p>
        <dl className="mt-5 grid grid-cols-2 gap-4">
          {[['Recortes', s?.cropRetentionDays], ['Registros', s?.logRetentionDays]].map(([k, v]) => (
            <div key={k} className="rounded-lg bg-sunken p-4"><dt className="text-xs text-ink-3">{k}</dt><dd className="mt-1 text-xl font-semibold tnum">{v ?? '…'} días</dd></div>
          ))}
        </dl>
      </Card>

      <Card className="p-6">
        <h2 className="font-semibold">Exportar</h2>
        <p className="mt-1 text-sm text-ink-2">Guarda las lecturas en un archivo CSV dentro de data/exports/.</p>
        <div className="mt-4 flex items-end gap-3">
          <label className="text-sm">
            <span className="mb-1 block text-xs text-ink-3">Estado</span>
            <select value={csvStatus} onChange={(e) => setCsvStatus(e.target.value as SightingStatus | 'all')} className="rounded-lg border border-line bg-surface px-3 py-2">
              <option value="all">Todas</option>
              {(Object.keys(statusMeta) as SightingStatus[]).map((k) => <option key={k} value={k}>{statusMeta[k].label}</option>)}
            </select>
          </label>
          <Button variant="primary" onClick={download}>Exportar CSV</Button>
        </div>
        {exported && <p role="status" className="mt-3 text-sm text-st-green">{exported}</p>}
      </Card>

      <Card className="border-st-red/30 p-6">
        <h2 className="font-semibold">Purgar datos vencidos</h2>
        <p className="mt-1 text-sm text-ink-2">Elimina recortes y registros que superan el plazo de retención. No se puede deshacer.</p>
        <Button variant="danger" className="mt-4" onClick={() => dialog.current?.showModal()}>Purgar datos vencidos</Button>
        {msg && <p role="status" className="mt-3 text-sm text-st-green">✓ {msg}</p>}
      </Card>

      <dialog ref={dialog} aria-labelledby="dlg-t" className="m-auto w-[min(440px,90vw)] rounded-xl border border-line bg-surface p-6 text-ink shadow-soft backdrop:bg-black/50">
        <h2 id="dlg-t" className="text-lg font-semibold">¿Purgar datos vencidos?</h2>
        <p className="mt-2 text-sm text-ink-2">Se eliminarán los recortes de más de {s?.cropRetentionDays} días y los registros de más de {s?.logRetentionDays} días. Esta acción no se puede deshacer.</p>
        <div className="mt-6 flex justify-end gap-2">
          <Button autoFocus onClick={() => dialog.current?.close()}>Cancelar</Button>
          <Button variant="danger" disabled={busy} onClick={purge}>{busy ? 'Purgando…' : 'Sí, purgar'}</Button>
        </div>
      </dialog>
    </div>
  )
}
