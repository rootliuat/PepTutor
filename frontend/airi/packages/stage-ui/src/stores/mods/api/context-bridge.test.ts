import { describe, expect, it } from 'vitest'

import { cloneChatStreamContextForBroadcast } from './context-bridge'

describe('cloneChatStreamContextForBroadcast', () => {
  it('drops non-cloneable values instead of breaking chat send hooks', () => {
    const nonCloneable = () => 'not cloneable'
    const context = {
      message: {
        role: 'user',
        content: ['hello', nonCloneable],
      },
      contexts: {
        lesson: [
          {
            id: 'ctx-1',
            contextId: 'ctx-1',
            content: ['lesson context', nonCloneable],
            createdAt: 1,
          },
        ],
      },
      composedMessage: [
        {
          role: 'user',
          content: ['hello', nonCloneable],
        },
      ],
      input: {
        type: 'input:text',
        data: {
          text: 'hello',
          dropped: nonCloneable,
        },
      },
    } as any

    expect(() => structuredClone(context)).toThrow()

    const cloned = cloneChatStreamContextForBroadcast(context)

    expect(cloned.message.content).toEqual(['hello', null])
    expect(cloned.contexts.lesson[0].content).toEqual(['lesson context', null])
    expect(cloned.composedMessage[0].content).toEqual(['hello', null])
    expect(cloned.input.data).toEqual({ text: 'hello' })
    expect(() => structuredClone(cloned)).not.toThrow()
  })
})
