import { expect, test, vi } from 'vitest'
import { ApiError, getJson, postJson, qs } from '@/api/http'

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

test('qs omite vacíos', () => {
  expect(qs({ a: 1, b: null, c: undefined, d: '' })).toBe('?a=1')
  expect(qs({})).toBe('')
})

test('getJson devuelve el JSON', async () => {
  const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { x: 1 }))
  vi.stubGlobal('fetch', fetchMock)
  await expect(getJson('/api/x')).resolves.toEqual({ x: 1 })
  expect(fetchMock).toHaveBeenCalledWith('/api/x', { credentials: 'same-origin' })
})

test('ApiError con detail', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(jsonResponse(404, { detail: 'avistamiento no encontrado' })))
  const notFound = await getJson('/api/x').catch((e: unknown) => e)
  expect(notFound).toBeInstanceOf(ApiError)
  expect((notFound as ApiError).status).toBe(404)
  expect((notFound as ApiError).detail).toBe('avistamiento no encontrado')

  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(new Response('no es json', { status: 500 })))
  const failed = await getJson('/api/x').catch((e: unknown) => e)
  expect(failed).toBeInstanceOf(ApiError)
  expect((failed as ApiError).status).toBe(500)
  expect((failed as ApiError).detail).toBe('error 500')
})

test('postJson envía JSON', async () => {
  const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, {}))
  vi.stubGlobal('fetch', fetchMock)
  await postJson('/api/x')
  const init = fetchMock.mock.calls[0][1] as RequestInit
  expect(init.method).toBe('POST')
  expect(init.headers).toMatchObject({ 'Content-Type': 'application/json' })
  expect(init.body).toBe('{}')
})
