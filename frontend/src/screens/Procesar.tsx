import { useEffect, useRef, useState } from 'react'
import { cancelRun, listProfiles, listVideos, startRun, subscribeRunProgress, type Profile, type RunEvent, type RunSummary, type Video } from '@/api'
import { Button, Card, PageHeader, Stat } from '@/components/ui'
import { fmtBytes, fmtPct, fmtSpeed, fmtTime } from '@/lib/format'

type Progress = Extract<RunEvent, { type: 'progress' }>

export default function Procesar({ onReview }: { onReview: (runId: number) => void }) {
  const [videos, setVideos] = useState<Video[] | null>(null)
  const [profiles, setProfiles] = useState<Profile[]>([])
  const [video, setVideo] = useState<string | null>(null)
  const [profile, setProfile] = useState('')
  const [jobId, setJobId] = useState<string | null>(null)
  const [failure, setFailure] = useState<string | null>(null)
  const [progress, setProgress] = useState<Progress | null>(null)
  const [summary, setSummary] = useState<RunSummary | null>(null)
  const unsub = useRef<() => void>(undefined)

  useEffect(() => {
    listVideos().then(setVideos, () => setVideos([]))
    listProfiles().then((ps) => {
      setProfiles(ps)
      setProfile((ps.find((p) => p.isDefault) ?? ps[0])?.id ?? '')
    }, () => setProfiles([]))
    return () => unsub.current?.()
  }, [])

  const start = async () => {
    const selected = videos?.find((v) => v.path === video)
    if (!selected) return
    setSummary(null)
    setFailure(null)
    try {
      const job = await startRun(selected, profile)
      setJobId(job.jobId)
      setProgress({ type: 'progress', fraction: null, processedMs: 0, durationMs: job.durationMs, plates: 0, speedFactor: null })
      unsub.current = subscribeRunProgress(job.jobId, (e) => {
        if (e.type === 'progress') setProgress(e)
        else if (e.type === 'done') { setSummary(e.summary); setProgress(null) }
        else {
          if (e.type === 'failed') setFailure(e.message)
          setProgress(null)
          setJobId(null)
        }
      })
    } catch (e) {
      setFailure(e instanceof Error ? e.message : 'Error al procesar')
    }
  }

  const running = progress !== null
  const groups: { mode: Profile['mode']; label: string }[] = [
    { mode: 'estatico', label: 'Cámara fija' },
    { mode: 'movil', label: 'Cámara en vehículo' },
  ]

  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader title="Procesar video" sub="El análisis se hace en este equipo; ningún video sale de aquí." />

      <section aria-labelledby="h-videos" className="mb-8">
        <h2 id="h-videos" className="mb-3 text-sm font-semibold text-ink-2">1 · Elige un video</h2>
        <Card className="overflow-hidden">
          <div role="radiogroup" aria-labelledby="h-videos">
            {!videos && [0, 1, 2].map((i) => <div key={i} className="m-4 h-8 rounded skeleton" />)}
            {videos?.map((v) => {
              const on = video === v.path
              return (
                <button key={v.name} role="radio" aria-checked={on} disabled={running} onClick={() => setVideo(v.path)}
                  className={`flex w-full items-center gap-4 border-b border-line px-5 py-3.5 text-left last:border-0 transition ${on ? 'bg-accent-soft' : 'hover:bg-sunken'}`}>
                  <span aria-hidden className={`grid h-4 w-4 place-items-center rounded-full border-2 ${on ? 'border-accent' : 'border-ink-3'}`}>{on && <span className="h-2 w-2 rounded-full bg-accent" />}</span>
                  <span className="flex-1 font-mono text-sm">{v.name}</span>
                  <span className="w-20 text-right text-sm text-ink-2 tnum">{v.durationMs === null ? '—' : fmtTime(v.durationMs)}</span>
                  <span className="w-20 text-right text-sm text-ink-3 tnum">{fmtBytes(v.sizeBytes)}</span>
                </button>
              )
            })}
          </div>
        </Card>
      </section>

      <section aria-labelledby="h-esc" className="mb-8">
        <h2 id="h-esc" className="mb-3 text-sm font-semibold text-ink-2">2 · Escenario</h2>
        <div role="radiogroup" aria-labelledby="h-esc" className="grid grid-cols-[3fr_1fr] gap-4 max-[900px]:grid-cols-1">
          {groups.map((g) => (
            <fieldset key={g.mode} className="rounded-xl border border-dashed border-line p-3">
              <legend className="px-2 text-xs font-medium uppercase tracking-wide text-ink-3">{g.label}</legend>
              <div className={`grid gap-3 ${g.mode === 'estatico' ? 'grid-cols-3 max-[700px]:grid-cols-1' : ''}`}>
                {profiles.filter((p) => p.mode === g.mode).map((p) => {
                  const on = profile === p.id
                  return (
                    <button key={p.id} role="radio" aria-checked={on} disabled={running} onClick={() => setProfile(p.id)}
                      className={`rounded-lg border p-4 text-left transition ${on ? 'border-accent bg-accent-soft ring-1 ring-accent' : 'border-line bg-surface hover:border-ink-3'}`}>
                      <div className="flex items-center justify-between font-semibold">{p.title}{on && <span aria-hidden className="text-accent">✓</span>}</div>
                      <div className="mt-1 text-sm text-ink-2">{p.description}</div>
                    </button>
                  )
                })}
              </div>
            </fieldset>
          ))}
        </div>
      </section>

      {failure && <p role="alert" className="mb-4 rounded-lg bg-st-red-soft p-4 text-sm font-medium text-st-red">{failure}</p>}

      {!running && !summary && (
        <div className="flex items-center gap-4">
          <Button variant="primary" className="px-8 py-3 text-base" disabled={!video} onClick={start}>Procesar</Button>
          {!video && <span className="text-sm text-ink-3">Elige un video para empezar.</span>}
        </div>
      )}

      {progress && jobId && (
        <Card className="anim-in p-6" >
          <div className="mb-3 flex items-center justify-between">
            <h2 className="font-semibold">Procesando <span className="font-mono text-sm font-normal text-ink-2">{video}</span></h2>
            <Button variant="secondary" onClick={() => cancelRun(jobId)}>Cancelar</Button>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-sunken" role="progressbar" aria-valuenow={Math.round((progress.fraction ?? 0) * 100)} aria-valuemin={0} aria-valuemax={100} aria-label="Progreso">
            <div className="h-full rounded-full bg-accent transition-[width] duration-150" style={{ width: `${(progress.fraction ?? 0) * 100}%` }} />
          </div>
          <div className="mt-2 text-sm text-ink-2 tnum" aria-live="polite">{fmtTime(progress.processedMs)}{progress.durationMs !== null && ` / ${fmtTime(progress.durationMs)}`}</div>
          <dl className="mt-5 grid grid-cols-3 gap-4">
            {[['Placas leídas', progress.plates], ['Velocidad', progress.speedFactor ? fmtSpeed(progress.speedFactor) : '—'], ['Avance', progress.fraction === null ? '—' : fmtPct(progress.fraction)]].map(([k, v]) => (
              <div key={k} className="rounded-lg bg-sunken p-4"><dt className="text-xs text-ink-3">{k}</dt><dd className="mt-1 text-xl font-semibold tnum">{v}</dd></div>
            ))}
          </dl>
        </Card>
      )}

      {summary && (
        <section className="anim-in" aria-labelledby="h-res">
          <h2 id="h-res" className="mb-3 text-sm font-semibold text-ink-2">Resultado</h2>
          <div className="grid grid-cols-5 gap-3 max-[1000px]:grid-cols-2">
            <Stat label="Legibles" value={summary.legible} />
            <Stat label="Por revisar" value={summary.unverified} />
            <Stat label="Ocultas por baja calidad" value={summary.hiddenLowQuality} />
            <Stat label="Confirmadas automáticamente" value={summary.autoConfirmed} />
            <Stat label="Duración" value={fmtTime(summary.durationMs)} />
          </div>
          <div className="mt-6 flex gap-3">
            <Button variant="primary" className="px-6 py-3 text-base" onClick={() => onReview(summary.runId)}>Revisar {summary.unverified} placas</Button>
            <Button variant="ghost" onClick={() => setSummary(null)}>Procesar otro video</Button>
          </div>
        </section>
      )}
    </div>
  )
}
