import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { decide, listRuns, listSightings, type Decision, type Run, type SightingList, type SightingTab } from '@/api'
import SightingCard, { SightingCardSkeleton } from '@/components/SightingCard'
import ReviewPanel from '@/components/ReviewPanel'
import FrameViewer from '@/components/FrameViewer'
import { isTyping, statusMeta } from '@/lib/format'

const plural: Record<string, string> = { unverified: 'Por revisar', confirmed: 'Confirmadas', corrected: 'Corregidas', rejected: 'Descartadas', illegible: 'Borrosas' }
const tabs: { id: SightingTab; label: string; icon?: string }[] = [
  ...(['unverified', 'confirmed', 'corrected', 'rejected', 'illegible'] as const).map((id) => ({ id, label: plural[id], icon: statusMeta[id].icon })),
  { id: 'all', label: 'Todas' },
]

const emptyText: Partial<Record<SightingTab, string>> = {
  unverified: 'No hay placas por revisar. ¡Todo al día!',
  hidden: 'No hay lecturas ocultas por baja calidad.',
}

const emptyCounts: Record<SightingTab, number> = { unverified: 0, confirmed: 0, corrected: 0, rejected: 0, illegible: 0, all: 0, hidden: 0 }

export default function Lecturas({ initialRunId }: { initialRunId: number | null }) {
  const [tab, setTab] = useState<SightingTab>('unverified')
  const [query, setQuery] = useState('')
  const [runId, setRunId] = useState<number | null>(initialRunId)
  const [runs, setRuns] = useState<Run[]>([])
  const [data, setData] = useState<SightingList | null>(null)
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [editing, setEditing] = useState(false)
  const [drawer, setDrawer] = useState(false)
  const [viewing, setViewing] = useState<'frame' | 'video' | null>(null)
  const grid = useRef<HTMLDivElement>(null)

  useEffect(() => { listRuns().then((r) => setRuns([...r].sort((a, b) => a.id - b.id)), () => setRuns([])) }, [])

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    let res: SightingList
    try {
      res = await listSightings({ tab, query, runId })
    } catch {
      res = { items: [], total: 0, counts: emptyCounts }
    }
    setData(res)
    setPage(1)
    setLoading(false)
    return res
  }, [tab, query, runId])

  const loadMore = async () => {
    if (!data) return
    try {
      const res = await listSightings({ tab, query, runId }, page + 1)
      setData({ ...res, items: [...data.items, ...res.items] })
      setPage(page + 1)
    } catch {
      return
    }
  }

  useEffect(() => {
    const t = setTimeout(() => load().then((r) => setSelectedId(r.items[0]?.id ?? null)), query ? 200 : 0)
    return () => clearTimeout(t)
  }, [load, query])

  const items = data?.items ?? []
  const idx = items.findIndex((s) => s.id === selectedId)
  const selected = idx >= 0 ? items[idx] : null
  const runIndex = useMemo(() => new Map(runs.map((r, i) => [r.id, i + 1])), [runs])

  const nextPendingId = (from: number) => {
    const order = [...items.slice(from + 1), ...items.slice(0, from)]
    return (order.find((s) => s.status === 'unverified') ?? order[0])?.id ?? null
  }

  const onDecide = async (d: Decision) => {
    if (!selected) return
    const next = nextPendingId(idx)
    await decide(selected.id, d)
    setEditing(false)
    const res = await load(true)
    const stillThere = res.items.find((s) => s.id === next) 
    setSelectedId(stillThere ? next : res.items.find((s) => s.status === 'unverified')?.id ?? res.items[0]?.id ?? null)
  }

  const onSkip = () => { if (idx >= 0) setSelectedId(nextPendingId(idx)) }

  const move = (delta: number) => {
    if (!items.length) return
    const n = Math.max(0, Math.min(items.length - 1, (idx < 0 ? 0 : idx) + delta))
    setSelectedId(items[n].id)
    grid.current?.querySelector<HTMLElement>(`[data-id="${items[n].id}"]`)?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }

  const cols = () => (grid.current ? getComputedStyle(grid.current).gridTemplateColumns.split(' ').length : 1)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (isTyping(e.target) || e.metaKey || e.ctrlKey || e.altKey || editing || viewing) return
      const k = e.key
      const map: Record<string, () => void> = {
        ArrowRight: () => move(1), ArrowLeft: () => move(-1), ArrowDown: () => move(cols()), ArrowUp: () => move(-cols()),
      }
      if (selected) Object.assign(map, {
        c: () => onDecide({ action: 'confirm' }), e: () => setEditing(true), r: () => onDecide({ action: 'reject' }),
        b: () => onDecide({ action: 'illegible' }), s: onSkip,
        v: () => setViewing('video'), f: () => setViewing('frame'),
      })
      const fn = map[k] ?? map[k.toLowerCase()]
      if (fn) { e.preventDefault(); fn() }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  const select = (id: number) => { setSelectedId(id); setEditing(false); setDrawer(true) }

  return (
    <div className="grid grid-cols-[1fr_400px] gap-8 max-[1180px]:grid-cols-1">
      <div className="min-w-0">
        <div className="mb-5 flex flex-wrap items-center gap-3">
          <h1 className="mr-auto text-2xl font-semibold tracking-tight">Lecturas</h1>
          <label className="relative">
            <span className="sr-only">Buscar por placa</span>
            <span aria-hidden className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-3">⌕</span>
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Buscar placa…" className="w-52 rounded-lg border border-line bg-surface py-2 pl-8 pr-3 text-sm uppercase placeholder:normal-case placeholder:text-ink-3" />
          </label>
          <label>
            <span className="sr-only">Video</span>
            <select value={runId ?? ''} onChange={(e) => setRunId(e.target.value ? Number(e.target.value) : null)} className="max-w-60 rounded-lg border border-line bg-surface px-3 py-2 text-sm">
              <option value="">Todos los videos</option>
              {runs.map((r) => <option key={r.id} value={r.id}>{r.video}</option>)}
            </select>
          </label>
        </div>

        <div role="tablist" aria-label="Estado" className="mb-6 flex flex-wrap items-center gap-1 border-b border-line">
          {tabs.map((t) => (
            <TabButton key={t.id} active={tab === t.id} onClick={() => setTab(t.id)} count={data?.counts[t.id]}>
              {t.icon && <span aria-hidden className="mr-1.5 opacity-70">{t.icon}</span>}{t.label}
            </TabButton>
          ))}
          <span className="ml-auto" />
          <TabButton active={tab === 'hidden'} onClick={() => setTab('hidden')} subtle>
            Ocultas por baja calidad ({data?.counts.hidden ?? '…'})
          </TabButton>
        </div>

        {loading ? (
          <div className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-4" aria-busy="true" aria-label="Cargando lecturas">
            {Array.from({ length: 9 }, (_, i) => <SightingCardSkeleton key={i} />)}
          </div>
        ) : items.length === 0 ? (
          <div className="anim-in grid place-items-center rounded-xl border border-dashed border-line px-6 py-20 text-center">
            <div aria-hidden className="mb-3 text-3xl text-st-green">✓</div>
            <p className="font-medium">{emptyText[tab] ?? 'No hay lecturas con estos filtros.'}</p>
            {query && <p className="mt-1 text-sm text-ink-3">Prueba con otra búsqueda o cambia de video.</p>}
          </div>
        ) : (
          <>
            <div ref={grid} className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-4">
              {items.map((s) => <SightingCard key={s.id} s={s} selected={s.id === selectedId} onSelect={() => select(s.id)} />)}
            </div>
            {items.length < (data?.total ?? 0) && (
              <div className="mt-6 flex justify-center">
                <button onClick={loadMore} className="rounded-lg border border-line px-5 py-2.5 text-sm font-medium transition hover:bg-sunken">Cargar más</button>
              </div>
            )}
          </>
        )}
      </div>

      {drawer && <div className="fixed inset-0 z-40 bg-black/40 min-[1181px]:hidden" onClick={() => setDrawer(false)} aria-hidden />}
      <aside
        aria-label="Panel de revisión"
        className={`self-start rounded-xl border border-line bg-surface p-5 shadow-soft min-[1181px]:sticky min-[1181px]:top-22 max-[1180px]:fixed max-[1180px]:inset-y-0 max-[1180px]:right-0 max-[1180px]:z-50 max-[1180px]:w-[400px] max-[1180px]:max-w-full max-[1180px]:overflow-y-auto max-[1180px]:rounded-none max-[1180px]:transition-transform ${drawer ? '' : 'max-[1180px]:translate-x-full'}`}
      >
        <button onClick={() => setDrawer(false)} className="mb-3 rounded-md px-2 py-1 text-sm text-ink-2 hover:bg-sunken min-[1181px]:hidden">✕ Cerrar</button>
        {loading ? (
          <div className="space-y-4" aria-hidden><div className="aspect-[3/1] rounded-lg skeleton" /><div className="mx-auto h-14 w-56 rounded skeleton" /><div className="h-24 rounded skeleton" /></div>
        ) : selected ? (
          <ReviewPanel s={selected} run={runs.find((r) => r.id === selected.runId)} runIndex={runIndex.get(selected.runId) ?? 0}
            editing={editing} setEditing={setEditing} onDecide={onDecide} onSkip={onSkip} onView={setViewing} />
        ) : (
          <p className="py-16 text-center text-sm text-ink-3">Selecciona una lectura para revisarla.</p>
        )}
      </aside>
      {viewing && selected && <FrameViewer key={selected.id} s={selected} videoName={runs.find((r) => r.id === selected.runId)?.video ?? ''} initial={viewing} onClose={() => setViewing(null)} />}
    </div>
  )
}

function TabButton({ active, subtle, count, onClick, children }: { active: boolean; subtle?: boolean; count?: number; onClick: () => void; children: React.ReactNode }) {
  return (
    <button role="tab" aria-selected={active} onClick={onClick}
      className={`-mb-px inline-flex items-center border-b-2 px-3 py-2.5 text-sm transition ${active ? 'border-accent font-semibold text-ink' : 'border-transparent text-ink-2 hover:text-ink'} ${subtle && !active ? 'text-xs text-ink-3' : ''}`}>
      {children}
      {count !== undefined && <span className={`ml-2 rounded-full px-1.5 text-xs tnum ${active ? 'bg-accent-soft text-accent' : 'bg-sunken text-ink-3'}`}>{count}</span>}
    </button>
  )
}
