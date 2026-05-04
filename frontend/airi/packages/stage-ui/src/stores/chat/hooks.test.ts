import { afterEach, describe, expect, it, vi } from 'vitest'

import { createChatHooks } from './hooks'

describe('createChatHooks', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('isolates failing side-effect hooks so chat send can continue', async () => {
    const hooks = createChatHooks()
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const secondHook = vi.fn()

    hooks.onBeforeMessageComposed(async () => {
      throw new DOMException('[object Array] could not be cloned.', 'DataCloneError')
    })
    hooks.onBeforeMessageComposed(async () => {
      secondHook()
    })

    await expect(hooks.emitBeforeMessageComposedHooks('hello', {
      message: { role: 'user', content: 'hello' },
      contexts: {},
    })).resolves.toBeUndefined()

    expect(secondHook).toHaveBeenCalledTimes(1)
    expect(warn).toHaveBeenCalledWith(
      '[chat-hooks] before-message-composed hook failed:',
      expect.any(DOMException),
    )
  })
})
