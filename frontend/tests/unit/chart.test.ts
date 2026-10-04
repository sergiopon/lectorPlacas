import { expect, test } from 'vitest'
import { lowerBound, upperBound } from '@/lib/chart'

test('upperBound ajusta al dato', () => {
  expect(upperBound([0.167, null], 0.08, 0.05)).toBeCloseTo(0.2, 6)
  expect(upperBound([0.03], 0.08, 0.05)).toBe(0.08)
  expect(upperBound([null], 0.08, 0.05)).toBe(0.08)
})

test('lowerBound ajusta al dato', () => {
  expect(lowerBound([0.62, 0.9], 0.8, 0.1)).toBeCloseTo(0.6, 6)
  expect(lowerBound([0.95], 0.8, 0.1)).toBe(0.8)
  expect(lowerBound([], 0.8, 0.1)).toBe(0.8)
})
