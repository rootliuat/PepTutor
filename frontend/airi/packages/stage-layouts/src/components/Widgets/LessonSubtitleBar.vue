<script setup lang="ts">
import { useChatSessionStore } from '@proj-airi/stage-ui/stores/chat/session-store'
import { useLessonStore } from '@proj-airi/stage-ui/stores/lesson'
import { useLessonAiriRuntimeStore } from '@proj-airi/stage-ui/stores/lesson-airi-runtime'
import { resolveLessonChatMessageText } from '@proj-airi/stage-ui/stores/lesson-chat-history'
import {
  joinLessonVisibleSegmentsForDisplay,
  normalizeLessonVisibleSegments,
  sanitizeLessonVisibleText,
} from '@proj-airi/stage-ui/utils/lesson-text'
import { storeToRefs } from 'pinia'
import { computed } from 'vue'

const lessonStore = useLessonStore()
const lessonAiriRuntime = useLessonAiriRuntimeStore()
const chatSessionStore = useChatSessionStore()

const { currentTeacherPrompt, activeTurn, transcript } = storeToRefs(lessonStore)
const { lastRecognizedText, liveTranscriptText } = storeToRefs(lessonAiriRuntime)
const { messages } = storeToRefs(chatSessionStore)

const subtitleText = computed(() => {
  const latestTranscriptText = sanitizeLessonVisibleText(
    [...transcript.value].reverse().find(entry => entry.speaker === 'teacher')?.text || '',
  )
  if (latestTranscriptText)
    return latestTranscriptText

  const latestAssistantMessage = [...messages.value].reverse().find(message => message.role === 'assistant')
  const latestAssistantText = latestAssistantMessage
    ? sanitizeLessonVisibleText(resolveLessonChatMessageText(latestAssistantMessage))
    : ''
  if (latestAssistantText)
    return latestAssistantText

  if (activeTurn.value) {
    const segments = normalizeLessonVisibleSegments(
      activeTurn.value.teacher_visible_segments,
      activeTurn.value.teacher_response,
    )
    const text = joinLessonVisibleSegmentsForDisplay(segments)
    if (text)
      return text
  }

  return sanitizeLessonVisibleText(currentTeacherPrompt.value || '') || '等待老师话术...'
})
</script>

<template>
  <div
    class="pointer-events-none mx-auto max-w-[38rem] w-full border border-sky-100/80 rounded-[24px] bg-[linear-gradient(135deg,rgba(255,255,255,0.9),rgba(240,249,255,0.76))] px-4 py-3 text-slate-900 shadow-[0_24px_70px_-45px_rgba(15,23,42,0.55)] backdrop-blur-xl md:max-w-[40rem] dark:border-white/14 dark:bg-[linear-gradient(135deg,rgba(7,12,20,0.88),rgba(15,23,42,0.72))] md:px-5 dark:text-white dark:shadow-[0_24px_70px_-35px_rgba(2,12,27,0.92)]"
  >
    <div class="flex items-start gap-3 text-left">
      <div class="h-10 w-10 flex shrink-0 items-center justify-center rounded-2xl bg-cyan-100/80 text-sm text-cyan-700 font-semibold ring-1 ring-cyan-200/90 ring-inset dark:bg-cyan-400/16 dark:text-cyan-100 dark:ring-cyan-300/20">
        米粒
      </div>

      <div class="min-w-0 flex-1">
        <div class="whitespace-pre-wrap text-sm text-slate-900 font-semibold leading-6 md:text-lg dark:text-white md:leading-7">
          {{ subtitleText }}
        </div>

        <div
          v-if="liveTranscriptText || lastRecognizedText"
          class="mt-2.5 flex flex-wrap items-center gap-2 text-xs text-slate-500 dark:text-neutral-200/78"
        >
          <span
            class="max-w-full truncate rounded-full bg-emerald-100/80 px-3 py-1.5 text-emerald-700 dark:bg-emerald-400/12 dark:text-emerald-100/90"
          >
            实时转写：{{ liveTranscriptText || lastRecognizedText }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>
