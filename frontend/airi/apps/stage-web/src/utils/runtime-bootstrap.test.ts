import { afterEach, describe, expect, it, vi } from 'vitest'

import { waitForOptionalInitialization } from './runtime-bootstrap'

describe('waitForOptionalInitialization', () => {
  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('returns without warning when the task resolves within the startup budget', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})

    await waitForOptionalInitialization(Promise.resolve(), {
      timeoutMs: 50,
      label: 'test task',
    })

    expect(warnSpy).not.toHaveBeenCalled()
  })

  it('logs a warning and continues when the task exceeds the startup budget', async () => {
    vi.useFakeTimers()
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})

    const pendingTask = new Promise<void>(() => {})
    const waitPromise = waitForOptionalInitialization(pendingTask, {
      timeoutMs: 50,
      label: 'slow task',
    })

    await vi.advanceTimersByTimeAsync(50)
    await waitPromise

    expect(warnSpy).toHaveBeenCalledWith('[runtime-bootstrap] slow task did not finish within 50ms; continuing startup.')
  })

  it('reports initialization errors through the provided error hook', async () => {
    const onError = vi.fn()
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const error = new Error('boom')

    await waitForOptionalInitialization(Promise.reject(error), {
      timeoutMs: 50,
      label: 'failing task',
      onError,
    })

    expect(onError).toHaveBeenCalledWith(error)
    expect(warnSpy).not.toHaveBeenCalled()
  })
})
