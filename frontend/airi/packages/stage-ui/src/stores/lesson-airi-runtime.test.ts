import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import { Emotion } from '../constants/emotions'
import { normalizeLessonPlaybackStopReason, resolveLessonInterruptDecision } from '../utils/lesson-interrupt-policy'
import { resolveLessonClassroomSimpleStatus, useLessonAiriRuntimeStore } from './lesson-airi-runtime'

describe('lesson AIRI runtime store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('keeps the latest backend performance plan available to the stage runtime', () => {
    const store = useLessonAiriRuntimeStore()
    const plan = {
      name: Emotion.Question,
      intensity: 0.78,
      motion: 'Think',
      expression: 'think',
      durationMs: 3600,
      reason: 'lesson_turn',
      teachingAction: 'hint',
      evaluation: 'unclear',
      turnLabel: 'answer_question',
      speechStyle: 'gentle_correction' as const,
      mouthIntensity: 0.65,
      interruptPolicy: 'finish_current_sentence' as const,
      contentSource: 'lesson_runtime_teacher_response',
      fallbackAllowed: false,
      performanceSource: 'lesson_persona_context',
      targetRole: 'question',
      expectedStudentAction: 'answer',
      speechStyleTag: 'short_scaffold',
    }

    store.applyPerformancePlan(plan)

    expect(store.currentPerformancePlan).toMatchObject({
      emotionName: Emotion.Question,
      emotionIntensity: 0.78,
      motion: 'Think',
      expression: 'think',
      durationMs: 3600,
      reason: 'lesson_turn',
      teachingAction: 'hint',
      evaluation: 'unclear',
      turnLabel: 'answer_question',
      speechStyle: 'gentle_correction',
      mouthIntensity: 0.65,
      interruptPolicy: 'finish_current_sentence',
      contentSource: 'lesson_runtime_teacher_response',
      fallbackAllowed: false,
      performanceSource: 'lesson_persona_context',
      targetRole: 'question',
      expectedStudentAction: 'answer',
      speechStyleTag: 'short_scaffold',
    })
    expect(store.currentPerformancePlan?.updatedAt).toBeGreaterThan(0)
    expect(store.currentSpeechStyle).toBe('gentle_correction')
    expect(store.currentMouthIntensity).toBe(0.65)
    expect(store.canDriveMouthOpen).toBe(false)
    expect(store.currentInterruptPolicy).toBe('finish_current_sentence')
    expect(store.canBargeInDuringTeacherSpeech).toBe(false)
    expect(store.performanceApplyStatus).toBe('pending')
    expect(store.performanceApplyStatusLabel).toBe('等待应用')
    expect(store.requestedMotion).toBe('Think')
    expect(store.requestedExpression).toBe('think')

    store.markPerformanceApplied({
      status: 'fallback',
      requestedMotion: 'Think',
      appliedMotion: 'Idle',
      requestedExpression: 'think',
      appliedExpression: 'motion-only',
      fallbackReason: 'live2d_motion_unavailable:Think',
    })

    expect(store.performanceApplyStatus).toBe('fallback')
    expect(store.performanceApplyStatusLabel).toBe('已降级')
    expect(store.appliedMotion).toBe('Idle')
    expect(store.appliedExpression).toBe('motion-only')
    expect(store.performanceFallbackReason).toBe('live2d_motion_unavailable:Think')
    expect(store.performanceFallbackKind).toBe('motion_unavailable')
    expect(store.performanceApplyUpdatedAt).toBeGreaterThan(0)

    store.applyPerformancePlan(plan)

    expect(store.performanceApplyStatus).toBe('fallback')
    expect(store.appliedMotion).toBe('Idle')
    expect(store.appliedExpression).toBe('motion-only')
    expect(store.performanceFallbackReason).toBe('live2d_motion_unavailable:Think')
  })

  it('defaults to barge-in allowed and clears stale performance on runtime reset', () => {
    const store = useLessonAiriRuntimeStore()

    expect(store.currentSpeechStyle).toBe('normal')
    expect(store.currentMouthIntensity).toBe(1)
    expect(store.canDriveMouthOpen).toBe(false)
    expect(store.currentInterruptPolicy).toBe('barge_in_allowed')
    expect(store.canBargeInDuringTeacherSpeech).toBe(true)

    store.applyPerformancePlan({
      name: Emotion.Happy,
      intensity: 0.92,
      interruptPolicy: 'no_interrupt',
      speechStyle: 'slow_split',
      mouthIntensity: 0.7,
    })
    store.resetRuntimeState()

    expect(store.currentPerformancePlan).toBeNull()
    expect(store.performanceApplyStatus).toBe('idle')
    expect(store.appliedMotion).toBe('')
    expect(store.performanceFallbackReason).toBe('')
    expect(store.currentSpeechStyle).toBe('normal')
    expect(store.currentMouthIntensity).toBe(1)
    expect(store.currentInterruptPolicy).toBe('barge_in_allowed')
    expect(store.canBargeInDuringTeacherSpeech).toBe(true)
  })

  it('resolves lesson barge-in decisions from the current interrupt policy', () => {
    expect(resolveLessonInterruptDecision({
      event: 'volume_barge_in',
      policy: 'barge_in_allowed',
    })).toMatchObject({
      rawStopReason: 'lesson-learner-barge-in',
      normalizedStopReason: 'volume_barge_in',
      shouldStopPlayback: true,
      shouldAbortActiveTurn: false,
      shouldMarkInterrupted: true,
      speechIntentBehavior: 'interrupt',
    })

    expect(resolveLessonInterruptDecision({
      event: 'final_transcript',
      policy: 'finish_current_sentence',
    })).toMatchObject({
      rawStopReason: 'lesson-learner-transcription',
      normalizedStopReason: 'final_transcript_interrupt',
      shouldStopPlayback: false,
      shouldAbortActiveTurn: false,
      shouldMarkInterrupted: false,
      speechIntentBehavior: 'queue',
    })

    expect(resolveLessonInterruptDecision({
      event: 'manual_send',
      policy: 'no_interrupt',
    })).toMatchObject({
      rawStopReason: 'lesson-learner-send',
      normalizedStopReason: 'manual_send_interrupt',
      shouldStopPlayback: false,
      shouldAbortActiveTurn: false,
      shouldMarkInterrupted: false,
      speechIntentBehavior: 'queue',
    })

    expect(resolveLessonInterruptDecision({
      event: 'stop_button',
      policy: 'no_interrupt',
    })).toMatchObject({
      rawStopReason: 'lesson-stop-button',
      normalizedStopReason: 'user_stop',
      shouldStopPlayback: true,
      shouldAbortActiveTurn: true,
      shouldMarkInterrupted: true,
      speechIntentBehavior: 'interrupt',
    })
  })

  it('normalizes playback stop reasons without losing the raw stop reason', () => {
    expect(normalizeLessonPlaybackStopReason('lesson-learner-barge-in')).toBe('volume_barge_in')
    expect(normalizeLessonPlaybackStopReason('lesson-learner-transcription')).toBe('final_transcript_interrupt')
    expect(normalizeLessonPlaybackStopReason('lesson-learner-send')).toBe('manual_send_interrupt')
    expect(normalizeLessonPlaybackStopReason('stage-unmount')).toBe('unmount_cleanup')
    expect(normalizeLessonPlaybackStopReason('lesson-stop-button')).toBe('user_stop')
  })

  it('maps lesson runtime signals to simple classroom status labels', () => {
    expect(resolveLessonClassroomSimpleStatus({ learnerSpeaking: true })).toBe('等待')
    expect(resolveLessonClassroomSimpleStatus({ learnerTyping: true })).toBe('等待')
    expect(resolveLessonClassroomSimpleStatus({ microphoneListening: true })).toBe('等待')
    expect(resolveLessonClassroomSimpleStatus({})).toBe('等待')
    expect(resolveLessonClassroomSimpleStatus({ backendLoading: true })).toBe('思考/说话中')
    expect(resolveLessonClassroomSimpleStatus({ assistantStreaming: true })).toBe('思考/说话中')
    expect(resolveLessonClassroomSimpleStatus({ teacherSpeaking: true })).toBe('思考/说话中')
    expect(resolveLessonClassroomSimpleStatus({ ttsSynthesisState: 'requesting' })).toBe('思考/说话中')
    expect(resolveLessonClassroomSimpleStatus({ ttsPlaybackState: 'playing' })).toBe('思考/说话中')
    expect(resolveLessonClassroomSimpleStatus({ connectionFailed: true })).toBe('未连接')
    expect(resolveLessonClassroomSimpleStatus({ unavailable: true })).toBe('不可用')
  })

  it('records speech synthesis and playback audit details', () => {
    const store = useLessonAiriRuntimeStore()

    store.markSpeechSynthesisStart({
      provider: 'peptutor-edge-tts',
      model: 'edge-tts',
      voice: 'zh-CN-XiaoxiaoNeural',
      text: 'Hello.',
      replyId: 'reply-1',
    })
    expect(store.ttsSynthesisState).toBe('requesting')
    expect(store.ttsPlaybackState).toBe('idle')
    store.markSpeechSynthesisHttpResult({
      status: 200,
      statusText: 'OK',
    })
    expect(store.ttsSynthesisState).toBe('http_ok')
    store.markSpeechSynthesisReady({
      audioByteLength: 4096,
      audioDurationMs: 1234.4,
    })

    expect(store.speechPlaybackStatus).toBe('decoded')
    expect(store.speechPlaybackProvider).toBe('peptutor-edge-tts')
    expect(store.speechSynthesisHttpStatus).toBe(200)
    expect(store.speechAudioByteLength).toBe(4096)
    expect(store.speechAudioDurationMs).toBe(1234)
    expect(store.speechSynthesisLatencyMs).toBeGreaterThanOrEqual(0)
    expect(store.speechPlaybackDebugLabel).toContain('TTS 已生成')
    expect(store.speechPlaybackDebugLabel).toContain('HTTP 200 OK')
    expect(store.speechPlaybackDebugLabel).toContain('synthesis=http_ok')
    expect(store.speechPlaybackDebugLabel).toContain('playback=idle')
    expect(store.speechPlaybackDebugLabel).toContain('4.0KB')
    expect(store.speechPlaybackDebugLabel).toContain('audio=1234ms')

    store.markSpeechPlaybackRequested({
      playbackId: 'playback-1',
      replyId: 'reply-1',
      audioContextState: 'running',
      reason: 'web_audio_buffer_source_start',
    })

    expect(store.ttsPlaybackState).toBe('play_requested')
    expect(store.ttsPlaybackReason).toBe('web_audio_buffer_source_start')
    expect(store.ttsPlaybackId).toBe('playback-1')
    expect(store.activeReplyId).toBe('reply-1')
    expect(store.ttsPlaybackStopReason).toBe('')
    expect(store.ttsPlaybackOverlapDetected).toBe(false)
    expect(store.teacherSpeaking).toBe(false)

    store.markSpeechPlaybackStart({
      playbackId: 'playback-1',
      replyId: 'reply-1',
      audioContextState: 'running',
    })

    expect(store.speechPlaybackStatus).toBe('playing')
    expect(store.ttsPlaybackState).toBe('playing')
    expect(store.canDriveMouthOpen).toBe(true)
    expect(store.teacherSpeaking).toBe(true)
    expect(store.classroomState).toBe('teacher_speaking')
    expect(store.speechPlaybackStartupLatencyMs).toBeGreaterThanOrEqual(0)

    store.markSpeechPlaybackEnd('ended', {
      playbackId: 'playback-1',
      replyId: 'reply-1',
      stopReason: 'ended',
    })

    expect(store.speechPlaybackStatus).toBe('ended')
    expect(store.ttsPlaybackState).toBe('ended')
    expect(store.ttsPlaybackStopReason).toBe('ended')
    expect(store.ttsPlaybackNormalizedStopReason).toBe('playback_ended')
    expect(store.canDriveMouthOpen).toBe(false)
    expect(store.teacherSpeaking).toBe(false)
    expect(store.speechPlaybackDurationMs).toBeGreaterThanOrEqual(0)
    expect(store.speechPlaybackDebugLabel).toContain('ctx=running')
  })

  it('keeps mouth-driving playback state intact while the next TTS segment is synthesized', () => {
    const store = useLessonAiriRuntimeStore()

    store.markSpeechSynthesisStart({
      provider: 'peptutor-edge-tts',
      model: 'edge-tts',
      voice: 'zh-CN-XiaoxiaoNeural',
      text: 'First sentence.',
      replyId: 'reply-1',
    })
    store.markSpeechSynthesisHttpResult({ status: 200, statusText: 'OK' })
    store.markSpeechSynthesisReady({ audioByteLength: 4096, audioDurationMs: 1000 })
    store.markSpeechPlaybackRequested({ playbackId: 'playback-1', replyId: 'reply-1', audioContextState: 'running' })
    store.markSpeechPlaybackStart({ playbackId: 'playback-1', replyId: 'reply-1', audioContextState: 'running' })

    store.markSpeechSynthesisStart({
      provider: 'peptutor-edge-tts',
      model: 'edge-tts',
      voice: 'zh-CN-XiaoxiaoNeural',
      text: 'Second sentence.',
      replyId: 'reply-2',
    })

    expect(store.ttsSynthesisState).toBe('requesting')
    expect(store.ttsPlaybackState).toBe('playing')
    expect(store.ttsPlaybackId).toBe('playback-1')
    expect(store.activeReplyId).toBe('reply-1')
    expect(store.speechPlaybackStatus).toBe('playing')
    expect(store.canDriveMouthOpen).toBe(true)

    store.markSpeechSynthesisHttpResult({ status: 200, statusText: 'OK' })
    store.markSpeechSynthesisReady({ audioByteLength: 2048, audioDurationMs: 700 })

    expect(store.ttsSynthesisState).toBe('http_ok')
    expect(store.ttsPlaybackState).toBe('playing')
    expect(store.ttsPlaybackId).toBe('playback-1')
    expect(store.activeReplyId).toBe('reply-1')
    expect(store.speechPlaybackStatus).toBe('playing')
    expect(store.canDriveMouthOpen).toBe(true)
  })

  it('keeps playback ownership stable when stale playback events arrive after a new playback starts', () => {
    const store = useLessonAiriRuntimeStore()

    store.markSpeechSynthesisStart({
      provider: 'peptutor-edge-tts',
      model: 'edge-tts',
      voice: 'zh-CN-XiaoxiaoNeural',
      text: 'First sentence.',
      replyId: 'reply-1',
    })
    store.markSpeechSynthesisReady()
    store.markSpeechPlaybackRequested({
      playbackId: 'playback-1',
      replyId: 'reply-1',
      audioContextState: 'running',
    })
    store.markSpeechPlaybackStart({
      playbackId: 'playback-1',
      replyId: 'reply-1',
      audioContextState: 'running',
    })

    store.markSpeechPlaybackRequested({
      playbackId: 'playback-2',
      replyId: 'reply-2',
      audioContextState: 'running',
      reason: 'web_audio_buffer_source_start',
    })

    expect(store.ttsPlaybackOverlapDetected).toBe(true)
    expect(store.ttsPlaybackOverlapCount).toBe(1)
    expect(store.ttsPlaybackId).toBe('playback-2')
    expect(store.activeReplyId).toBe('reply-2')
    expect(store.ttsPlaybackState).toBe('play_requested')

    store.markSpeechPlaybackEnd('ended', {
      playbackId: 'playback-1',
      replyId: 'reply-1',
      stopReason: 'stale-ended',
    })

    expect(store.ttsPlaybackId).toBe('playback-2')
    expect(store.activeReplyId).toBe('reply-2')
    expect(store.ttsPlaybackState).toBe('play_requested')
    expect(store.ttsPlaybackStopReason).toBe('')

    store.markSpeechPlaybackStart({
      playbackId: 'playback-2',
      replyId: 'reply-2',
      audioContextState: 'running',
    })
    store.markSpeechPlaybackEnd('interrupted', {
      playbackId: 'playback-2',
      replyId: 'reply-2',
      stopReason: 'new-message',
    })

    expect(store.ttsPlaybackState).toBe('interrupted')
    expect(store.ttsPlaybackReason).toBe('new-message')
    expect(store.ttsPlaybackStopReason).toBe('new-message')
    expect(store.ttsPlaybackNormalizedStopReason).toBe('new_teacher_turn_replace')
    expect(store.canDriveMouthOpen).toBe(false)

    store.resetRuntimeState()

    expect(store.ttsPlaybackId).toBe('')
    expect(store.activeReplyId).toBe('')
    expect(store.ttsPlaybackStopReason).toBe('')
    expect(store.ttsPlaybackNormalizedStopReason).toBe('')
    expect(store.ttsPlaybackOverlapDetected).toBe(false)
    expect(store.ttsPlaybackOverlapCount).toBe(0)
  })

  it('keeps the failed TTS stage and HTTP status visible for diagnostics', () => {
    const store = useLessonAiriRuntimeStore()

    store.markSpeechSynthesisStart({
      provider: 'peptutor-edge-tts',
      model: 'edge-tts',
      voice: 'zh-CN-XiaoxiaoNeural',
      text: 'Hello.',
    })
    store.markSpeechPlaybackError('Edge proxy failed.', {
      stage: 'synthesis',
      httpStatus: 502,
      httpStatusText: 'Bad Gateway',
    })

    expect(store.speechPlaybackStatus).toBe('error')
    expect(store.ttsSynthesisState).toBe('http_error')
    expect(store.ttsPlaybackState).toBe('skipped')
    expect(store.speechPlaybackFailureStage).toBe('synthesis')
    expect(store.speechSynthesisHttpStatus).toBe(502)
    expect(store.speechPlaybackDebugLabel).toContain('Edge proxy failed.')
    expect(store.speechPlaybackDebugLabel).toContain('HTTP 502 Bad Gateway')
    expect(store.speechPlaybackDebugLabel).toContain('stage=synthesis')

    store.resetRuntimeState()

    expect(store.speechPlaybackStatus).toBe('idle')
    expect(store.ttsSynthesisState).toBe('idle')
    expect(store.ttsPlaybackState).toBe('idle')
    expect(store.speechPlaybackDebugLabel).toBe('待命')
    expect(store.speechSynthesisHttpStatus).toBeNull()
    expect(store.speechPlaybackFailureStage).toBe('')
  })

  it('keeps TTS configuration failures visible instead of silently dropping playback', () => {
    const store = useLessonAiriRuntimeStore()

    store.markSpeechPlaybackError('TTS provider is not configured.', {
      stage: 'configuration',
    })

    expect(store.speechPlaybackStatus).toBe('error')
    expect(store.ttsSynthesisState).toBe('unsupported_provider')
    expect(store.ttsPlaybackState).toBe('skipped')
    expect(store.speechPlaybackFailureStage).toBe('configuration')
    expect(store.speechPlaybackDebugLabel).toContain('TTS provider is not configured.')
    expect(store.speechPlaybackDebugLabel).toContain('stage=configuration')
  })

  it('classifies browser playback failures separately from TTS synthesis', () => {
    const store = useLessonAiriRuntimeStore()

    store.markSpeechSynthesisStart({
      provider: 'peptutor-edge-tts',
      model: 'edge-tts',
      voice: 'zh-CN-XiaoxiaoNeural',
      text: 'Hello.',
    })
    store.markSpeechSynthesisHttpResult({ status: 200, statusText: 'OK' })
    store.markSpeechSynthesisReady({ audioByteLength: 2048, audioDurationMs: 800 })
    store.markSpeechPlaybackRequested({ audioContextState: 'suspended' })
    store.markSpeechPlaybackError('AudioContext remained suspended after resume().', {
      stage: 'audio_context',
      playbackState: 'audio_context_suspended',
      reason: 'audio_context_suspended',
    })

    expect(store.ttsSynthesisState).toBe('http_ok')
    expect(store.ttsPlaybackState).toBe('audio_context_suspended')
    expect(store.ttsPlaybackReason).toBe('audio_context_suspended')
    expect(store.speechPlaybackDebugLabel).toContain('synthesis=http_ok')
    expect(store.speechPlaybackDebugLabel).toContain('playback=audio_context_suspended')
    expect(store.teacherSpeaking).toBe(false)
    expect(store.canDriveMouthOpen).toBe(false)
  })

  it('classifies unavailable Live2D expressions as a known capability gap', () => {
    const store = useLessonAiriRuntimeStore()

    store.markPerformanceApplied({
      status: 'fallback',
      requestedMotion: 'Think',
      appliedMotion: 'FlickDown',
      requestedExpression: 'soft_smile',
      appliedExpression: 'motion-only',
      fallbackReason: 'live2d_motion_alias:Think->FlickDown;live2d_expression_unavailable:soft_smile',
    })

    expect(store.performanceFallbackKind).toBe('known_capability_gap')
    expect(store.performanceFallbackReason).toContain('live2d_expression_unavailable:soft_smile')
  })
})
