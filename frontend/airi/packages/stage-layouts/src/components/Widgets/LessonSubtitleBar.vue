<script setup lang="ts">
import { useLessonStore } from '@proj-airi/stage-ui/stores/lesson'
import { useLessonAiriRuntimeStore } from '@proj-airi/stage-ui/stores/lesson-airi-runtime'
import { stripLessonMarkdown } from '@proj-airi/stage-ui/utils/lesson-text'
import { storeToRefs } from 'pinia'
import { computed } from 'vue'

const lessonStore = useLessonStore()
const lessonAiriRuntime = useLessonAiriRuntimeStore()

const { currentPageTitle, currentTeacherPrompt, activeTurn } = storeToRefs(lessonStore)
const { lastRecognizedText, liveTranscriptText } = storeToRefs(lessonAiriRuntime)

const subtitleText = computed(() =>
  stripLessonMarkdown(activeTurn.value?.teacher_response || '')
  || stripLessonMarkdown(currentTeacherPrompt.value || '')
  || '等待老师话术...',
)
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
    class="pointer-events-none mx-auto w-full max-w-[38rem] rounded-[24px] border border-sky-100/80 bg-[linear-gradient(135deg,rgba(255,255,255,0.9),rgba(240,249,255,0.76))] px-4 py-3 text-slate-900 shadow-[0_24px_70px_-45px_rgba(15,23,42,0.55)] backdrop-blur-xl md:max-w-[40rem] md:px-5 dark:border-white/14 dark:bg-[linear-gradient(135deg,rgba(7,12,20,0.88),rgba(15,23,42,0.72))] dark:text-white dark:shadow-[0_24px_70px_-35px_rgba(2,12,27,0.92)]"
  >
    <div class="flex items-start gap-3 text-left">
      <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-cyan-100/80 text-sm font-semibold text-cyan-700 ring-1 ring-inset ring-cyan-200/90 dark:bg-cyan-400/16 dark:text-cyan-100 dark:ring-cyan-300/20">
        米粒
      </div>

      <div class="min-w-0 flex-1">
        <div class="flex flex-wrap items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.22em] text-sky-700/72 dark:text-cyan-100/72">
          <span>{{ subtitleSpeakerLabel }}</span>
          <span class="rounded-full bg-sky-100/80 px-2.5 py-1 text-[10px] tracking-[0.18em] text-slate-500 dark:bg-white/8 dark:text-neutral-200/85">
            {{ subtitleContext }}
          </span>
        </div>

        <div class="mt-2 text-sm font-semibold leading-6 text-slate-900 md:text-lg md:leading-7 dark:text-white">
          {{ subtitleText }}
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
