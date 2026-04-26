import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import { useCharacterNotebookStore } from './notebook'

describe('store character notebook', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('stores transcript entries as local diary mirrors', () => {
    const store = useCharacterNotebookStore()

    const entry = store.addTranscriptEntry('Learner: hello\nTeacher: hi', {
      metadata: {
        source: 'lesson-backend-transcript-mirror',
        memoryAuthority: 'backend',
      },
    })

    expect(entry.kind).toBe('diary')
    expect(store.transcriptEntries).toHaveLength(1)
    expect(store.partitionDiary).toEqual(store.transcriptEntries)
    expect(store.debugEntries).toHaveLength(0)
    expect(store.transcriptEntries[0]?.metadata).toMatchObject({
      source: 'lesson-backend-transcript-mirror',
      memoryAuthority: 'backend',
    })
  })

  it('keeps the legacy diary API as an alias of transcript entries', () => {
    const store = useCharacterNotebookStore()

    store.addDiaryEntry('Legacy diary alias still maps to transcript entries.')

    expect(store.transcriptEntries).toHaveLength(1)
    expect(store.transcriptEntries[0]?.kind).toBe('diary')
  })

  it('separates debug notes from transcript entries', () => {
    const store = useCharacterNotebookStore()

    store.addDebugEntry('backend writeback degraded')
    store.addTranscriptEntry('Learner: help me')

    expect(store.debugEntries).toHaveLength(1)
    expect(store.transcriptEntries).toHaveLength(1)
    expect(store.debugEntries[0]?.kind).toBe('note')
    expect(store.transcriptEntries[0]?.kind).toBe('diary')
  })
})
