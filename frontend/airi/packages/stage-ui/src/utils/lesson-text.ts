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
