<script setup lang="ts">
import { useLessonStore } from '@proj-airi/stage-ui/stores/lesson'
import { useLessonAiriRuntimeStore } from '@proj-airi/stage-ui/stores/lesson-airi-runtime'
import { segmentLessonTeacherReply } from '@proj-airi/stage-ui/utils/lesson-text'
import { storeToRefs } from 'pinia'
import { computed } from 'vue'

const lessonStore = useLessonStore()
const lessonAiriRuntime = useLessonAiriRuntimeStore()

const { currentPageTitle, currentTeacherPrompt, activeTurn } = storeToRefs(lessonStore)
const { lastRecognizedText, liveTranscriptText } = storeToRefs(lessonAiriRuntime)

const subtitleSegments = computed(() => {
  const activeSegments = segmentLessonTeacherReply(activeTurn.value?.teacher_response || '')
  if (activeSegments.length > 0)
    return activeSegments

  const promptSegments = segmentLessonTeacherReply(currentTeacherPrompt.value || '')
  if (promptSegments.length > 0)
    return promptSegments

  return ['等待老师话术...']
})
const subtitleSpeakerLabel = computed(() =>
  activeTurn.value?.turn_label === 'page_entry'
    ? '米粒老师开场讲解'
    : '米粒老师当前台词',
)
const subtitleContext = computed(() =>
  activeTurn.value?.block_uid
  || currentPageTitle.value
  || 'lesson runtime',
)
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
        <div class="flex flex-wrap items-center gap-2 text-[11px] text-sky-700/72 font-semibold tracking-[0.22em] uppercase dark:text-cyan-100/72">
          <span>{{ subtitleSpeakerLabel }}</span>
          <span class="rounded-full bg-sky-100/80 px-2.5 py-1 text-[10px] text-slate-500 tracking-[0.18em] dark:bg-white/8 dark:text-neutral-200/85">
            {{ subtitleContext }}
          </span>
        </div>

        <div class="mt-2 text-sm text-slate-900 font-semibold leading-6 space-y-1.5 md:text-lg dark:text-white md:leading-7">
          <div
            v-for="(segment, index) in subtitleSegments"
            :key="`${subtitleContext}:${index}:${segment}`"
          >
            {{ segment }}
          </div>
        </div>

        <div class="mt-2.5 flex flex-wrap items-center gap-2 text-xs text-slate-500 dark:text-neutral-200/78">
          <span class="rounded-full bg-sky-100/70 px-3 py-1.5 dark:bg-white/8">
            {{ currentPageTitle }}
          </span>
          <span
            v-if="liveTranscriptText || lastRecognizedText"
            class="max-w-full truncate rounded-full bg-emerald-100/80 px-3 py-1.5 text-emerald-700 dark:bg-emerald-400/12 dark:text-emerald-100/90"
          >
            实时转写：{{ liveTranscriptText || lastRecognizedText }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>
