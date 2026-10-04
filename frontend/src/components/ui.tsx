import type { ReactNode } from 'react'
import type { SightingStatus } from '@/api'
import { fmtPct, formatPlate, statusMeta } from '@/lib/format'

export function Plate({ text, size = 'md' }: { text: string; size?: 'sm' | 'md' | 'lg' }) {
  const s = { sm: 'text-base px-2 py-0.5 border-2', md: 'text-xl px-3 py-1 border-2', lg: 'text-4xl px-5 py-2 border-[3px]' }[size]
  return (
    <span className={`inline-block rounded-md border-black bg-[#f2c200] font-black tracking-wider text-black tnum ${s}`} style={{ fontFamily: "'Arial Black', Arial, sans-serif" }}>
      {formatPlate(text)}
    </span>
  )
}

export function StatusBadge({ status }: { status: SightingStatus }) {
  const m = statusMeta[status]
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ${m.tone}`}>
      <span aria-hidden>{m.icon}</span>
      {m.label}
    </span>
  )
}

export function ConfidenceBar({ value, wide }: { value: number; wide?: boolean }) {
  const tone = value >= 0.85 ? 'bg-st-green' : value >= 0.6 ? 'bg-st-amber' : 'bg-st-red'
  return (
    <div className="flex items-center gap-2" title="Seguridad del lector">
      <div className={`h-1.5 overflow-hidden rounded-full bg-sunken ${wide ? 'flex-1' : 'w-16'}`} role="meter" aria-valuenow={Math.round(value * 100)} aria-valuemin={0} aria-valuemax={100} aria-label="Seguridad del lector">
        <div className={`h-full rounded-full ${tone}`} style={{ width: `${value * 100}%` }} />
      </div>
      <span className="text-xs text-ink-2 tnum">{fmtPct(value)}</span>
    </div>
  )
}

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`rounded-xl border border-line bg-surface shadow-soft ${className}`}>{children}</div>
}

export function Button({ variant = 'secondary', className = '', ...p }: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'secondary' | 'danger' | 'ghost' }) {
  const v = {
    primary: 'bg-accent text-accent-ink hover:brightness-110',
    secondary: 'border border-line bg-surface text-ink hover:bg-sunken',
    danger: 'bg-st-red text-white dark:text-black hover:brightness-110',
    ghost: 'text-ink-2 hover:bg-sunken hover:text-ink',
  }[variant]
  return <button {...p} className={`inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-50 ${v} ${className}`} />
}

export function Kbd({ children }: { children: ReactNode }) {
  return <kbd className="rounded border border-current/30 px-1.5 py-px font-mono text-[11px] opacity-80">{children}</kbd>
}

export function PageHeader({ title, sub, children }: { title: string; sub?: string; children?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {sub && <p className="mt-1 text-sm text-ink-3">{sub}</p>}
      </div>
      {children}
    </div>
  )
}

export function Stat({ label, value, sub }: { label: string; value: ReactNode; sub?: string }) {
  return (
    <Card className="p-5">
      <div className="text-xs font-medium uppercase tracking-wide text-ink-3">{label}</div>
      <div className="mt-2 text-3xl font-semibold tracking-tight tnum">{value}</div>
      {sub && <div className="mt-1 text-sm text-ink-3 tnum">{sub}</div>}
    </Card>
  )
}
