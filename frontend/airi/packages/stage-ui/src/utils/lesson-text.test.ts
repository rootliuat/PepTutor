import { describe, expect, it } from 'vitest'

import { stripLessonMarkdown } from './lesson-text'

describe('stripLessonMarkdown', () => {
  it('removes emphasis and inline markdown syntax from lesson speech text', () => {
    expect(stripLessonMarkdown('Say **hungry** and then `drink`.')).toBe('Say hungry and then drink.')
  })

  it('keeps link labels while removing markdown links and act tokens', () => {
    expect(stripLessonMarkdown('<|ACT {"emotion":"happy"}|>Read [hungry](https://example.com) aloud.')).toBe('Read hungry aloud.')
  })
})
