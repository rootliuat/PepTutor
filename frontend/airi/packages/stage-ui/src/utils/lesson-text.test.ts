import { describe, expect, it } from 'vitest'

import {
  firstLessonCaptionSegment,
  sanitizeLessonVisibleText,
  segmentLessonTeacherReply,
  stripLessonMarkdown,
} from './lesson-text'

describe('stripLessonMarkdown', () => {
  it('removes emphasis and inline markdown syntax from lesson speech text', () => {
    expect(stripLessonMarkdown('Say **hungry** and then `drink`.')).toBe('Say hungry and then drink.')
  })

  it('keeps link labels while removing markdown links and act tokens', () => {
    expect(stripLessonMarkdown('<|ACT {"emotion":"happy"}|>Read [hungry](https://example.com) aloud.')).toBe('Read hungry aloud.')
  })
})

describe('sanitizeLessonVisibleText', () => {
  it('removes visible emotion tags, source references, and lesson section headers', () => {
    expect(sanitizeLessonVisibleText(
      '[neutral] 好，我们来看这一页。\n[教材知识点摘要]\n这一页练 hungry。[见TB-G5S1U3-P31-B1]\n[练习建议]\n跟我读一遍。',
    )).toBe('好，我们来看这一页。\n这一页练 hungry。\n跟我读一遍。')
  })

  it('removes internal labels from student-visible text', () => {
    expect(sanitizeLessonVisibleText(
      '[joy] 英文目标：确认歌唱比赛不在五月。动作：跟老师读一遍 No。target_role question route answer_turn_policy',
    )).toBe('确认歌唱比赛不在五月。跟老师读一遍 No。 question')
  })
})

describe('segmentLessonTeacherReply', () => {
  it('splits long mixed teacher replies into readable chunks', () => {
    const segments = segmentLessonTeacherReply(
      `[neutral] 这一页是一个关于制作沙拉的连环画故事。小熊Zoom说"I'm hungry."，小松鼠Zip帮他去菜园摘蔬菜，一起洗菜、切菜，最后做出健康的农场晚餐。[应用场景]\n比如你饿了想和朋友一起做饭，可以说："I'm hungry. Let's make a salad!"`,
      { maxLength: 54 },
    )

    expect(segments.length).toBeGreaterThan(2)
    expect(segments.join('\n')).not.toContain('[neutral]')
    expect(segments.join('\n')).not.toContain('[应用场景]')
    expect(segments.some(segment => segment.includes('小熊Zoom'))).toBe(true)
  })

  it('keeps short English classroom phrases intact', () => {
    expect(segmentLessonTeacherReply('跟我说：I\'m hungry.')).toContain('跟我说：I\'m hungry.')
    expect(segmentLessonTeacherReply('对，就是 It\'s in May.')).toContain('对，就是 It\'s in May.')
    expect(segmentLessonTeacherReply('完整说：No, it isn\'t.')).toContain('完整说：No, it isn\'t.')
  })

  it('does not use an isolated translation fragment as the caption', () => {
    expect(firstLessonCaptionSegment('（我饿了）。\n跟我读：I\'m hungry.')).toBe('跟我读：I\'m hungry.')
  })
})
