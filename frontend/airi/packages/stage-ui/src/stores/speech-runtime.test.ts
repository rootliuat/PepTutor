import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useSpeechRuntimeStore } from './speech-runtime'

describe('store speech runtime', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('forwards playback stop controls to the registered controller', () => {
    const store = useSpeechRuntimeStore()
    const stopByOwner = vi.fn()
    const stopAll = vi.fn()

    store.registerPlaybackController({
      stopByOwner,
      stopAll,
    })

    store.stopByOwner('peptutor-lesson', 'lesson-interrupt')
    store.stopAll('lesson-reset')

    expect(stopByOwner).toHaveBeenCalledWith('peptutor-lesson', 'lesson-interrupt')
    expect(stopAll).toHaveBeenCalledWith('lesson-reset')

    store.clearPlaybackController()
    store.stopByOwner('ignored-owner', 'ignored-reason')

    expect(stopByOwner).toHaveBeenCalledTimes(1)
  })

  it('can dispose a stale host and register the next stage host', async () => {
    const store = useSpeechRuntimeStore()
    const firstIntent = { intentId: 'first' }
    const secondIntent = { intentId: 'second' }
    const firstHost = {
      openIntent: vi.fn(() => firstIntent),
    }
    const secondHost = {
      openIntent: vi.fn(() => secondIntent),
    }

    await store.registerHost(firstHost as unknown as Parameters<typeof store.registerHost>[0])

    expect(store.isHost()).toBe(true)
    expect(store.openIntent()).toBe(firstIntent)

    await store.dispose()
    await store.registerHost(secondHost as unknown as Parameters<typeof store.registerHost>[0])

    expect(store.isHost()).toBe(true)
    expect(store.openIntent()).toBe(secondIntent)
    expect(firstHost.openIntent).toHaveBeenCalledTimes(1)
    expect(secondHost.openIntent).toHaveBeenCalledTimes(1)
  })
})
