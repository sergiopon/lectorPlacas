import { expect, test, vi } from 'vitest'
import { exportCsv, getMetrics, getSightingFrame, listProfiles, listSightings, subscribeRunProgress } from '@/api'
import type { Sighting } from '@/api'

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

function stubRoutes(routes: Record<string, () => Response>) {
  const fetchMock = vi.fn((path: string) => {
    const route = routes[path.split('?')[0]]
    return Promise.resolve(route ? route() : jsonResponse(404, { detail: 'no encontrado' }))
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function paramsOf(url: string): URLSearchParams {
  return new URLSearchParams(url.split('?')[1] ?? '')
}

test('listProfiles mapea campos', async () => {
  stubRoutes({
    '/api/profiles': () =>
      jsonResponse(200, [{ name: 'patrulla', label: 'Patrulla', description: 'd', mode: 'movil', default: false }]),
  })
  await expect(listProfiles()).resolves.toEqual([
    { id: 'patrulla', title: 'Patrulla', description: 'd', mode: 'movil', isDefault: false },
  ])
})

test('listSightings construye la consulta', async () => {
  const fetchMock = stubRoutes({
    '/api/sightings': () => jsonResponse(200, { items: [], total: 0, page: 1, pageSize: 50 }),
    '/api/sighting-counts': () => jsonResponse(200, {}),
  })
  await listSightings({ tab: 'unverified', query: ' abc-1 ', runId: 3 })
  const urls = fetchMock.mock.calls.map((c) => c[0] as string)
  const list = urls.find((u) => u.startsWith('/api/sightings?'))!
  const counts = urls.find((u) => u.startsWith('/api/sighting-counts?'))!
  expect(paramsOf(list)).toEqual(new URLSearchParams('q=ABC1&run=3&status=unverified&hidden=false&page=1'))
  expect(paramsOf(counts)).toEqual(new URLSearchParams('q=ABC1&run=3'))

  fetchMock.mockClear()
  await listSightings({ tab: 'hidden', query: ' abc-1 ', runId: 3 })
  const hidden = fetchMock.mock.calls.map((c) => c[0] as string).find((u) => u.startsWith('/api/sightings?'))!
  expect(paramsOf(hidden).get('hidden')).toBe('true')
  expect(paramsOf(hidden).has('status')).toBe(false)
})

test('getMetrics sin datos', async () => {
  stubRoutes({
    '/api/metrics': () => jsonResponse(404, { detail: 'sin datos' }),
    '/api/metrics/runs': () => jsonResponse(200, []),
    '/api/runs': () => jsonResponse(200, { items: [], page: 1, pageSize: 50 }),
  })
  const noData = { value: null, sub: 'Sin datos todavía' }
  await expect(getMetrics()).resolves.toEqual({
    auditedAccuracy: noData,
    fullPlateReads: noData,
    charErrorRate: noData,
    autoConfirmRate: noData,
    perVideo: [],
  })
})

test('exportCsv devuelve el nombre', async () => {
  const fetchMock = stubRoutes({ '/api/export': () => jsonResponse(200, { file: 'x.csv' }) })
  await expect(exportCsv('all')).resolves.toBe('x.csv')
  const init = (fetchMock.mock.calls[0] as unknown[])[1] as RequestInit
  expect(JSON.parse(init.body as string)).toEqual({ status: null })
})

class FakeEventSource {
  static last: FakeEventSource
  closed = false
  onerror: (() => void) | null = null
  private handlers: Record<string, ((ev: MessageEvent<string>) => void)[]> = {}

  constructor(public url: string) {
    FakeEventSource.last = this
  }

  addEventListener(type: string, fn: (ev: MessageEvent<string>) => void) {
    ;(this.handlers[type] ??= []).push(fn)
  }

  emit(type: string, data: unknown) {
    const ev = { data: JSON.stringify(data) } as MessageEvent<string>
    for (const fn of this.handlers[type] ?? []) fn(ev)
  }

  close() {
    this.closed = true
  }
}

test('subscribeRunProgress mapea eventos', () => {
  vi.stubGlobal('EventSource', FakeEventSource)
  const events: unknown[] = []
  subscribeRunProgress('job1', (e) => events.push(e))
  FakeEventSource.last.emit('progress', { positionMs: 1000, durationMs: 20000, fraction: 0.05, sightingsSaved: 2 })
  expect(events[0]).toMatchObject({ type: 'progress', processedMs: 1000, durationMs: 20000, fraction: 0.05, plates: 2 })
  expect(events[0]).toHaveProperty('speedFactor')

  FakeEventSource.last.emit('done', { state: 'cancelled' })
  expect(events[1]).toEqual({ type: 'cancelled' })
  expect(FakeEventSource.last.closed).toBe(true)
})

test('getSightingFrame prefiere frameMs', () => {
  const s = {
    id: 7, runId: 1, vehicleType: 'car', plateText: 'ABC123', ocrText: 'ABC123', confidence: 0.9, agreement: 1,
    numReadings: 3, status: 'unverified', reasons: [], hiddenLowQuality: false, duplicates: 0, firstSeenMs: 1000,
    lastSeenMs: 3000, frameMs: null, cropUrl: null, duplicateOf: null, reviewedAt: null,
  } as Sighting
  expect(getSightingFrame({ ...s, frameMs: 1200 }).timestampMs).toBe(1200)
  expect(getSightingFrame(s).timestampMs).toBe(2000)
  expect(getSightingFrame(s).frameUrl).toBe('/api/sightings/7/frame')
})
