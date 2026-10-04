function clean(r: number): number {
  return Math.round(r * 1000) / 1000
}

function present(values: (number | null)[]): number[] {
  return values.filter((v): v is number => v !== null)
}

export function upperBound(values: (number | null)[], minHi: number, step: number): number {
  const nums = present(values)
  if (nums.length === 0) return minHi
  const m = Math.max(...nums)
  return clean(Math.max(minHi, Math.ceil(m / step) * step))
}

export function lowerBound(values: (number | null)[], maxLo: number, step: number): number {
  const nums = present(values)
  if (nums.length === 0) return maxLo
  const m = Math.min(...nums)
  return clean(Math.min(maxLo, Math.floor(m / step) * step))
}
