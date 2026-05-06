export function stripLessonMarkdown(text: string): string {
  return stripLessonMarkdownSyntax(text)
    .replace(/\s+/g, ' ')
    .trim()
}

function stripLessonMarkdownSyntax(text: string): string {
  return text
    .replace(/<\|ACT[\s\S]*?\|>/g, ' ')
    .replace(/!\[([^\]]*)\]\([^)]+\)/g, '$1')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/`{1,3}([^`]+)`{1,3}/g, '$1')
    .replace(/(\*\*|__)(.*?)\1/g, '$2')
    .replace(/(^|[\s(])(\*|_)([^*_]+)\2(?=[\s).,!?:;，。！？；：]|$)/g, '$1$3')
    .replace(/~~(.*?)~~/g, '$1')
    .replace(/^[>\-+*#\s]+/gm, '')
}

const visibleEmotionTagPattern = /^\s*\[(?:neutral|joy|happy|sad|thinking|angry|surprised|question|confused|calm|serious|encouraging|gentle)[^\]]*\]\s*/gim
const visibleSectionHeaderPattern = /\s*\[(?:教材知识点摘要|应用场景|练习建议)\]\s*/g
const visibleSourceRefPattern = /\s*\[见\s*TB-[^\]]+\]\s*/gi
const visibleInternalLabelsPattern = /英文目标\s*[:：]\s*|动作\s*[:：]\s*|target_role|expected_student_action|answer_scope|TeachingMove|\b[\w-]*route[\w-]*\b|\b[\w-]*policy[\w-]*\b|\bdebug\b|statepatch/gi
const visibleBlankLinePattern = /[ \t]*\n[ \t]*/g
const displaySegmentMaxLength = 90

export type LessonVisibleSegmentKind = 'ack' | 'scaffold' | 'target' | 'action' | 'other'

export interface LessonVisibleSegment {
  segment_id: string
  sequence: number
  segment_kind: LessonVisibleSegmentKind
  display_text: string
  tts_text: string
  caption_text: string
  emotion?: string | null
}

export interface LessonVisibleSegmentInput {
  display_text?: unknown
  tts_text?: unknown
  caption_text?: unknown
  segment_id?: unknown
  sequence?: unknown
  segment_kind?: unknown
  emotion?: unknown
}

export interface LessonVisibleChatMessage {
  id: string
  role: string
  text: string
  createdAt?: unknown
}

export function sanitizeLessonVisibleText(text: string): string {
  return stripLessonMarkdownSyntax(text)
    .replace(visibleEmotionTagPattern, '')
    .replace(visibleSectionHeaderPattern, match => match.includes('\n') ? '\n' : ' ')
    .replace(visibleSourceRefPattern, match => match.includes('\n') ? '\n' : ' ')
    .replace(visibleInternalLabelsPattern, '')
    .replace(visibleBlankLinePattern, '\n')
    .replace(/[ \t]{2,}/g, ' ')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

export function segmentLessonTeacherReply(
  text: string,
  options: { maxLength?: number } = {},
): string[] {
  const sanitized = sanitizeLessonVisibleText(text)
  if (!sanitized)
    return []

  const maxLength = options.maxLength ?? displaySegmentMaxLength
  const segments: string[] = []
  const rawParts = sanitized
    .split(/\n+/)
    .map(part => part.trim())
    .filter(Boolean)

  for (const rawPart of rawParts) {
    for (const sentence of splitVisibleLessonSentence(rawPart, maxLength)) {
      const clean = sentence.trim()
      if (!clean)
        continue
      if (isIsolatedTranslationFragment(clean) && segments.length > 0) {
        segments[segments.length - 1] = `${segments[segments.length - 1]}${clean}`
        continue
      }
      segments.push(clean)
    }
  }

  return segments
}

export function firstLessonCaptionSegment(text: string): string {
  const segments = segmentLessonTeacherReply(text, { maxLength: 76 })
  return segments.find(segment => !isIsolatedTranslationFragment(segment)) || segments[0] || ''
}

export function buildLessonVisibleSegments(
  text: string,
  options: { maxLength?: number } = {},
): LessonVisibleSegment[] {
  return segmentLessonTeacherReply(text, options).map((segment, index) => ({
    segment_id: `teacher-visible-${index + 1}`,
    sequence: index,
    segment_kind: inferLessonVisibleSegmentKind(segment),
    display_text: segment,
    tts_text: segment,
    caption_text: segment,
    emotion: null,
  }))
}

export function normalizeLessonVisibleSegments(
  segments: LessonVisibleSegmentInput[] | null | undefined,
  fallbackText: string,
): LessonVisibleSegment[] {
  const normalized: LessonVisibleSegment[] = []

  for (const [index, segment] of (segments || []).entries()) {
    const displayText = sanitizeLessonVisibleText(String(segment.display_text ?? ''))
    if (!displayText)
      continue

    const ttsText = sanitizeLessonVisibleText(String(segment.tts_text ?? displayText)) || displayText
    const captionText = sanitizeLessonVisibleText(String(segment.caption_text ?? displayText)) || displayText

    normalized.push({
      segment_id: String(segment.segment_id || `teacher-visible-${index + 1}`),
      sequence: typeof segment.sequence === 'number' && Number.isFinite(segment.sequence) ? segment.sequence : index,
      segment_kind: isLessonVisibleSegmentKind(segment.segment_kind) ? segment.segment_kind : inferLessonVisibleSegmentKind(displayText),
      display_text: displayText,
      tts_text: ttsText,
      caption_text: captionText,
      emotion: typeof segment.emotion === 'string' ? segment.emotion : null,
    })
  }

  normalized.sort((left, right) => left.sequence - right.sequence)

  return normalized.length > 0 ? normalized : buildLessonVisibleSegments(fallbackText)
}

export function joinLessonVisibleSegmentsForDisplay(segments: LessonVisibleSegment[]): string {
  return segments.map(segment => segment.display_text).filter(Boolean).join('\n')
}

export function joinLessonVisibleSegmentsForSpeech(segments: LessonVisibleSegment[]): string {
  return segments.map(segment => segment.tts_text || segment.display_text).filter(Boolean).join(' ')
}

export function coalesceAdjacentLessonVisibleMessages<T extends LessonVisibleChatMessage>(messages: T[]): T[] {
  const merged: T[] = []

  for (const message of messages) {
    const text = message.text.trim()
    if (!text)
      continue

    const previous = merged[merged.length - 1]
    if (
      previous
      && previous.role === message.role
      && message.role !== 'user'
      && message.role !== 'error'
    ) {
      previous.id = `${previous.id}:${message.id}`
      previous.text = [previous.text, text].filter(Boolean).join('\n')
      previous.createdAt = message.createdAt ?? previous.createdAt
      continue
    }

    merged.push({
      ...message,
      text,
    })
  }

  return merged
}

function splitVisibleLessonSentence(text: string, maxLength: number): string[] {
  const chunks: string[] = []
  let buffer = ''

  for (const char of text) {
    buffer += char
    if (/[。！？；!?;]/.test(char)) {
      flushBuffer()
    }
    else if (/[：:]/.test(char) && visibleTextLength(buffer) >= Math.min(36, maxLength)) {
      flushBuffer()
    }
    else if (visibleTextLength(buffer) >= maxLength && /[\s，,、]/.test(char)) {
      flushBuffer()
    }
  }

  flushBuffer()
  return chunks

  function flushBuffer() {
    const clean = buffer.trim()
    if (clean)
      chunks.push(clean)
    buffer = ''
  }
}

function visibleTextLength(text: string): number {
  return [...text].length
}

function isIsolatedTranslationFragment(text: string): boolean {
  return /^["“”']?[（(][^）)]{1,24}[）)][。.!！?？]?["“”']?$/.test(text.trim())
}

function inferLessonVisibleSegmentKind(text: string): LessonVisibleSegmentKind {
  const normalized = text.trim()
  if (/^(?:好|对|没关系|我听到|意思对|这里|先别急|我们慢慢来)/.test(normalized))
    return 'ack'
  if (['意思是', '可以用', '句型', '这个词', '这里是', '里的', '要连起来读', '老师问的是', '故事里'].some(signal => normalized.includes(signal)))
    return 'scaffold'
  if (['跟我', '你先', '试试', '说一遍', '读一遍', '回答', '先试', '再自然说一遍'].some(signal => normalized.includes(signal)))
    return 'action'
  if (/[a-z]/i.test(normalized))
    return 'target'
  return 'other'
}

function isLessonVisibleSegmentKind(value: unknown): value is LessonVisibleSegmentKind {
  return value === 'ack'
    || value === 'scaffold'
    || value === 'target'
    || value === 'action'
    || value === 'other'
}
