export class ApiError extends Error {
  status: number
  detail: string

  constructor(status: number, detail: string) {
    super(detail)
    this.status = status
    this.detail = detail
  }
}

async function parse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = 'error ' + res.status
    try {
      const body = await res.json()
      if (body && typeof body.detail === 'string') detail = body.detail
    } catch {
      detail = 'error ' + res.status
    }
    throw new ApiError(res.status, detail)
  }
  return res.json() as Promise<T>
}

export async function getJson<T>(path: string): Promise<T> {
  return parse<T>(await fetch(path, { credentials: 'same-origin' }))
}

export async function postJson<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body ?? {}),
  })
  return parse<T>(res)
}

export function qs(params: Record<string, string | number | boolean | null | undefined>): string {
  const sp = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v === null || v === undefined || v === '') continue
    sp.set(k, String(v))
  }
  const s = sp.toString()
  return s ? '?' + s : ''
}
