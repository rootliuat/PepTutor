import type { EmotionPayload } from '../constants/emotions'

export type LessonInterruptPolicy = NonNullable<EmotionPayload['interruptPolicy']>

export type LessonInterruptEvent
  = | 'volume_barge_in'
    | 'final_transcript'
    | 'manual_send'
    | 'auto_send'
    | 'new_teacher_turn'
    | 'stop_button'

export type LessonInterruptStopReason
  = | 'volume_barge_in'
    | 'final_transcript_interrupt'
    | 'manual_send_interrupt'
    | 'auto_send_interrupt'
    | 'new_teacher_turn_replace'
    | 'lesson_turn_abort'
    | 'unmount_cleanup'
    | 'user_stop'
    | 'playback_ended'
    | 'playback_error'
    | 'unknown'

export interface LessonInterruptDecision {
  event: LessonInterruptEvent
  policy: LessonInterruptPolicy
  rawStopReason: string
  normalizedStopReason: LessonInterruptStopReason
  shouldStopPlayback: boolean
  shouldAbortActiveTurn: boolean
  shouldMarkInterrupted: boolean
  speechIntentBehavior: 'queue' | 'interrupt' | 'replace'
}

const EVENT_STOP_REASON: Record<LessonInterruptEvent, {
  raw: string
  normalized: LessonInterruptStopReason
}> = {
  volume_barge_in: {
    raw: 'lesson-learner-barge-in',
    normalized: 'volume_barge_in',
  },
  final_transcript: {
    raw: 'lesson-learner-transcription',
    normalized: 'final_transcript_interrupt',
  },
  manual_send: {
    raw: 'lesson-learner-send',
    normalized: 'manual_send_interrupt',
  },
  auto_send: {
    raw: 'lesson-learner-send',
    normalized: 'auto_send_interrupt',
  },
  new_teacher_turn: {
    raw: 'new-message',
    normalized: 'new_teacher_turn_replace',
  },
  stop_button: {
    raw: 'lesson-stop-button',
    normalized: 'user_stop',
  },
}

export function normalizeLessonInterruptPolicy(policy?: string | null): LessonInterruptPolicy {
  if (policy === 'finish_current_sentence' || policy === 'no_interrupt')
    return policy
  return 'barge_in_allowed'
}

export function normalizeLessonPlaybackStopReason(reason?: string | null): LessonInterruptStopReason {
  const normalized = reason?.trim() || ''
  if (!normalized)
    return 'unknown'

  if (normalized === 'lesson-learner-barge-in')
    return 'volume_barge_in'
  if (normalized === 'lesson-learner-transcription')
    return 'final_transcript_interrupt'
  if (normalized === 'lesson-learner-send')
    return 'manual_send_interrupt'
  if (normalized === 'new-message' || normalized === 'replace')
    return 'new_teacher_turn_replace'
  if (normalized === 'lesson-new-turn' || normalized.includes('lesson-turn-abort'))
    return 'lesson_turn_abort'
  if (normalized === 'stage-unmount')
    return 'unmount_cleanup'
  if (normalized === 'lesson-stop-button')
    return 'user_stop'
  if (normalized === 'ended')
    return 'playback_ended'
  if (normalized.includes('error') || normalized.includes('rejected') || normalized.includes('suspended'))
    return 'playback_error'

  return 'unknown'
}

export function resolveLessonInterruptDecision(options: {
  event: LessonInterruptEvent
  policy?: string | null
}): LessonInterruptDecision {
  const policy = normalizeLessonInterruptPolicy(options.policy)
  const reason = EVENT_STOP_REASON[options.event]
  const allowImmediateStop = policy === 'barge_in_allowed' || options.event === 'stop_button'

  return {
    event: options.event,
    policy,
    rawStopReason: reason.raw,
    normalizedStopReason: reason.normalized,
    shouldStopPlayback: allowImmediateStop,
    shouldAbortActiveTurn: allowImmediateStop && options.event !== 'volume_barge_in' && options.event !== 'new_teacher_turn',
    shouldMarkInterrupted: allowImmediateStop && options.event !== 'new_teacher_turn',
    speechIntentBehavior: allowImmediateStop ? 'interrupt' : 'queue',
  }
}
