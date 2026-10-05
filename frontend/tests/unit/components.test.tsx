import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, test, vi } from 'vitest'
import type { Sighting } from '@/api'
import FrameViewer from '@/components/FrameViewer'
import ReviewPanel from '@/components/ReviewPanel'
import SightingCard from '@/components/SightingCard'

function makeSighting(over: Partial<Sighting> = {}): Sighting {
  return {
    id: 1,
    runId: 1,
    vehicleType: 'car',
    plateText: 'ABC123',
    ocrText: 'ABC123',
    confidence: 0.9,
    agreement: 1,
    numReadings: 3,
    status: 'unverified',
    reasons: [],
    hiddenLowQuality: false,
    duplicates: 0,
    firstSeenMs: 42_000,
    lastSeenMs: 45_000,
    frameMs: null,
    cropUrl: null,
    duplicateOf: null,
    reviewedAt: null,
    ...over,
  }
}

test('SightingCard sin recorte', () => {
  render(<SightingCard s={makeSighting({ cropUrl: null })} selected={false} onSelect={() => {}} />)
  expect(screen.getByText('Sin recorte')).toBeInTheDocument()
  expect(screen.queryByRole('img')).toBeNull()
})

test('ReviewPanel acciones', async () => {
  const user = userEvent.setup()
  const onDecide = vi.fn()
  const onView = vi.fn()
  render(
    <ReviewPanel
      s={makeSighting({ firstSeenMs: 42_000 })}
      runIndex={1}
      editing={false}
      setEditing={() => {}}
      onDecide={onDecide}
      onSkip={() => {}}
      onView={onView}
    />,
  )
  await user.click(screen.getByRole('button', { name: /Es correcta/ }))
  expect(onDecide).toHaveBeenCalledWith({ action: 'confirm' })
  await user.click(screen.getByRole('button', { name: /Ir al video/ }))
  expect(onView).toHaveBeenCalledWith('video')
  expect(screen.getByText(/aparece en 0:42/)).toBeInTheDocument()
})

test('FrameViewer sin video', () => {
  HTMLDialogElement.prototype.showModal = vi.fn()
  const { container } = render(
    <FrameViewer s={makeSighting()} videoName="demo.mp4" initial="video" onClose={() => {}} />,
  )
  const video = container.querySelector('video')!
  fireEvent.error(video)
  expect(screen.getByText('El video original no está disponible')).toBeInTheDocument()
})

test('FrameViewer usa el instante de la lectura', () => {
  HTMLDialogElement.prototype.showModal = vi.fn()
  render(
    <FrameViewer s={makeSighting({ frameMs: 43_500 })} videoName="v.mp4" initial="frame" onClose={() => {}} />,
  )
  expect(screen.getByText('Fotograma en 0:43')).toBeInTheDocument()
})
