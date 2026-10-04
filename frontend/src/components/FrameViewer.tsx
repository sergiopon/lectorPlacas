import { useEffect, useRef, useState } from 'react'
import { getSightingFrame, getVideoSource, type Sighting } from '@/api'
import { Button, Kbd, Plate } from '@/components/ui'
import { fmtTime } from '@/lib/format'

type View = 'frame' | 'video'

export default function FrameViewer({ s, videoName, initial, onClose }: { s: Sighting; videoName: string; initial: View; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null)
  const video = useRef<HTMLVideoElement>(null)
  const [view, setView] = useState<View>(initial)
  const [frameFailed, setFrameFailed] = useState(false)
  const [videoFailed, setVideoFailed] = useState(false)
  const frame = getSightingFrame(s)
  const source = getVideoSource(s.runId, videoName)

  useEffect(() => {
    dialog.current?.showModal()
  }, [])

  const seek = () => { if (video.current) video.current.currentTime = Math.max(0, s.firstSeenMs / 1000 - 1) }
  const tab = (id: View, label: string) => (
    <button role="tab" aria-selected={view === id} onClick={() => setView(id)}
      className={`rounded-md px-3 py-1.5 text-sm font-medium transition ${view === id ? 'bg-surface text-ink shadow-soft' : 'text-ink-2 hover:text-ink'}`}>{label}</button>
  )

  return (
    <dialog ref={dialog} onClose={onClose} aria-labelledby="fv-t"
      className="m-auto w-[min(1100px,94vw)] rounded-xl border border-line bg-surface p-0 text-ink shadow-soft backdrop:bg-black/60">
      <div className="flex flex-wrap items-center gap-4 border-b border-line px-5 py-3">
        <h2 id="fv-t" className="sr-only">Placa en el video</h2>
        <Plate text={s.plateText} size="sm" />
        <span className="text-sm text-ink-2 tnum">aparece en {fmtTime(s.firstSeenMs)}–{fmtTime(s.lastSeenMs)}</span>
        <div role="tablist" className="ml-auto flex gap-1 rounded-lg bg-sunken p-1">
          {tab('frame', 'Captura completa')}
          {tab('video', 'Video')}
        </div>
        <Button variant="ghost" className="px-2.5" onClick={() => dialog.current?.close()} aria-label="Cerrar">✕</Button>
      </div>

      <div className="bg-sunken p-4">
        {view === 'frame' ? (
          frameFailed ? (
            <div className="anim-in grid aspect-video place-items-center rounded-lg border border-dashed border-line text-center">
              <div className="max-w-sm">
                <p className="font-medium">El fotograma no está disponible</p>
              </div>
            </div>
          ) : (
            <figure className="anim-in">
              <div className="relative overflow-hidden rounded-lg bg-black">
                <img src={frame.frameUrl} alt={`Fotograma completo en ${fmtTime(frame.timestampMs)} con la placa ${s.plateText}`} className="block w-full" onError={() => setFrameFailed(true)} />
              </div>
              <figcaption className="mt-2 flex justify-between text-xs text-ink-3 tnum">
                <span>Fotograma en {fmtTime(frame.timestampMs)}</span>
              </figcaption>
            </figure>
          )
        ) : !videoFailed ? (
          <video ref={video} src={source.url} controls autoPlay className="anim-in aspect-video w-full rounded-lg bg-black" onLoadedMetadata={seek} onError={() => setVideoFailed(true)} />
        ) : (
          <div className="anim-in grid aspect-video place-items-center rounded-lg border border-dashed border-line text-center">
            <div className="max-w-sm">
              <p className="font-medium">El video original no está disponible</p>
              <p className="mt-1 text-sm text-ink-3">No se encontró <span className="font-mono">{source.name}</span>. Cuando esté, se abrirá en {fmtTime(Math.max(0, s.firstSeenMs - 1000))}, un segundo antes de que aparezca la placa.</p>
              <Button className="mt-4" onClick={() => setView('frame')}>Ver la captura completa</Button>
            </div>
          </div>
        )}
      </div>
      <p className="px-5 py-2.5 text-xs text-ink-3"><Kbd>Esc</Kbd> cierra</p>
    </dialog>
  )
}
