import { useEffect, useState } from 'react'
import { getPendingCount, onDataChange } from '@/api'
import Procesar from '@/screens/Procesar'
import Lecturas from '@/screens/Lecturas'
import Metricas from '@/screens/Metricas'
import Historial from '@/screens/Historial'
import Ajustes from '@/screens/Ajustes'

export type Screen = 'procesar' | 'lecturas' | 'metricas' | 'historial' | 'ajustes'
type Theme = 'system' | 'light' | 'dark'

const nav: { id: Screen; label: string }[] = [
  { id: 'procesar', label: 'Procesar' },
  { id: 'lecturas', label: 'Lecturas' },
  { id: 'metricas', label: 'Métricas' },
  { id: 'historial', label: 'Historial' },
  { id: 'ajustes', label: 'Ajustes' },
]

function useTheme() {
  const [theme, setTheme] = useState<Theme>(() => (localStorage.getItem('tema') as Theme) || 'system')
  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const apply = () => document.documentElement.classList.toggle('dark', theme === 'dark' || (theme === 'system' && mq.matches))
    apply()
    localStorage.setItem('tema', theme)
    mq.addEventListener('change', apply)
    return () => mq.removeEventListener('change', apply)
  }, [theme])
  return [theme, setTheme] as const
}

export default function App() {
  const [screen, setScreen] = useState<Screen>('procesar')
  const [runFilter, setRunFilter] = useState<number | null>(null)
  const [pending, setPending] = useState(0)
  const [theme, setTheme] = useTheme()

  useEffect(() => {
    const load = () => void getPendingCount().then(setPending, () => setPending(0))
    load()
    return onDataChange(load)
  }, [])

  const openReadings = (runId: number | null) => {
    setRunFilter(runId)
    setScreen('lecturas')
  }

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-30 border-b border-line bg-surface/90 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-[1600px] items-center gap-8 px-6">
          <div className="flex items-center gap-2.5">
            <span aria-hidden className="grid h-7 w-10 place-items-center rounded-md border-2 border-black bg-[#f2c200] text-[10px] font-black text-black">ABC</span>
            <span className="font-semibold tracking-tight">lectorPlacas</span>
          </div>
          <nav aria-label="Principal" className="flex gap-1">
            {nav.map((n) => (
              <button
                key={n.id}
                onClick={() => setScreen(n.id)}
                aria-current={screen === n.id ? 'page' : undefined}
                className={`rounded-lg px-3 py-1.5 text-sm font-medium transition ${screen === n.id ? 'bg-accent-soft text-accent' : 'text-ink-2 hover:bg-sunken hover:text-ink'}`}
              >
                {n.label}
              </button>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-3">
            <button onClick={() => openReadings(null)} className="inline-flex items-center gap-2 rounded-full bg-st-amber-soft px-3 py-1 text-sm font-semibold text-st-amber tnum">
              <span aria-hidden>◷</span>
              {pending} por revisar
            </button>
            <label className="sr-only" htmlFor="tema">Tema</label>
            <select id="tema" value={theme} onChange={(e) => setTheme(e.target.value as Theme)} className="rounded-lg border border-line bg-surface px-2 py-1.5 text-sm text-ink-2">
              <option value="system">Tema del sistema</option>
              <option value="light">Claro</option>
              <option value="dark">Oscuro</option>
            </select>
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-[1600px] flex-1 px-6 py-8">
        {screen === 'procesar' && <Procesar onReview={openReadings} />}
        {screen === 'lecturas' && <Lecturas initialRunId={runFilter} />}
        {screen === 'metricas' && <Metricas />}
        {screen === 'historial' && <Historial onOpen={openReadings} />}
        {screen === 'ajustes' && <Ajustes />}
      </main>
    </div>
  )
}
