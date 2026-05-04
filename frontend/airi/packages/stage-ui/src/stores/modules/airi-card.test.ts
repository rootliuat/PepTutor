import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { createPepTutorLessonSessionSystemPrompt, PEPTUTOR_TEACHER_SESSION_CHARACTER_ID } from '../../constants/peptutor-teacher-card'
import { useAiriCardStore } from './airi-card'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (key: string, fallback?: string) => fallback ?? key,
  }),
}))

function createLocalStorageMock() {
  const backingStore = new Map<string, string>()

  return {
    getItem(key: string) {
      return backingStore.has(key) ? backingStore.get(key)! : null
    },
    setItem(key: string, value: string) {
      backingStore.set(key, String(value))
    },
    removeItem(key: string) {
      backingStore.delete(key)
    },
    clear() {
      backingStore.clear()
    },
    key(index: number) {
      return [...backingStore.keys()][index] ?? null
    },
    get length() {
      return backingStore.size
    },
  }
}

describe('airi card store', () => {
  beforeEach(() => {
    vi.stubGlobal('localStorage', createLocalStorageMock())
    setActivePinia(createPinia())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('initializes the default PepTutor teacher card on a clean profile', () => {
    const store = useAiriCardStore()

    expect(store.activeCard).toBeUndefined()

    store.initialize()

    expect(store.activeCardId).toBe('default')
    expect(store.activeCard?.name).toBe('米粒')
    expect(store.activeCard?.nickname).toBe('mili')
    expect(store.getCard('default')?.metadata?.conf_uid).toBe('zh_mili_01')
    expect(store.systemPrompt).toContain('base.prompt.prefix')
    expect(store.systemPrompt).toContain('PepTutor 的女性小学英语教师')
    expect(store.systemPrompt).toContain('广西师范大学')
    expect(store.systemPrompt).toContain('海鲜螺蛳粉')
    expect(store.systemPrompt).toContain('周末喜欢去海边看日落')
    expect(store.systemPrompt).toContain('这是出厂设置，不是剧本')
    expect(store.systemPrompt).toContain('永远先接住情绪')
    expect(store.systemPrompt).toContain('后端 LessonRuntime')
    expect(store.activeCard?.greetings).toEqual([])
    expect(store.activeCard?.messageExample).toEqual([])
  })

  it('exposes a lesson-scoped Mili session prompt without default AIRI lore', () => {
    const prompt = createPepTutorLessonSessionSystemPrompt()

    expect(PEPTUTOR_TEACHER_SESSION_CHARACTER_ID).toBe('peptutor-mili-teacher')
    expect(prompt).toContain('你是米粒（Mili）')
    expect(prompt).toContain('Teacher Kernel and LessonRuntime decide teaching facts')
    expect(prompt).toContain('Do not import AIRI/Neko Ayaka default lore')
  })

  it('does not overwrite an existing default card', () => {
    const store = useAiriCardStore()
    store.cards.set('default', {
      name: 'Custom Teacher',
      version: '1.0.0',
      description: 'Existing card',
      creator: '',
      notes: '',
      personality: '',
      scenario: '',
      greetings: [],
      greetingsGroupOnly: [],
      messageExample: [],
      tags: [],
      extensions: {
        airi: {
          modules: {
            consciousness: {
              provider: '',
              model: '',
            },
            speech: {
              provider: '',
              model: '',
              voice_id: '',
            },
            displayModelId: 'preset-live2d-1',
          },
          agents: {},
        },
      },
    })

    store.initialize()

    expect(store.getCard('default')?.name).toBe('Custom Teacher')
  })
})
