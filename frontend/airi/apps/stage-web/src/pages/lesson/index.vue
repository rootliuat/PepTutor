<script setup lang="ts">
import Header from '@proj-airi/stage-layouts/components/Layouts/Header.vue'
import LessonInteractiveArea from '@proj-airi/stage-layouts/components/Layouts/LessonInteractiveArea.vue'
import MobileHeader from '@proj-airi/stage-layouts/components/Layouts/MobileHeader.vue'
import LessonRuntimeChatPanel from '@proj-airi/stage-layouts/components/Widgets/LessonRuntimeChatPanel.vue'
import LessonSidebar from '@proj-airi/stage-layouts/components/Widgets/LessonSidebar.vue'
import LessonSubtitleBar from '@proj-airi/stage-layouts/components/Widgets/LessonSubtitleBar.vue'

import { BackgroundProvider } from '@proj-airi/stage-layouts/components/Backgrounds'
import { useBackgroundThemeColor } from '@proj-airi/stage-layouts/composables/theme-color'
import { useBackgroundStore } from '@proj-airi/stage-layouts/stores/background'
import { WidgetStage } from '@proj-airi/stage-ui/components/scenes'
import { useLessonStore } from '@proj-airi/stage-ui/stores/lesson'
import { useLessonChatHistoryStore } from '@proj-airi/stage-ui/stores/lesson-chat-history'
import { ensureLessonHearingFallbackProvider } from '@proj-airi/stage-ui/stores/lesson-voice-hearing-fallback'
import { ensureLessonSpeechFallbackProvider } from '@proj-airi/stage-ui/stores/lesson-voice-speech-fallback'
import { bootstrapPepTutorBackendAuth } from '@proj-airi/stage-ui/stores/peptutor-backend-auth'
import { bootstrapPepTutorVoiceEnvDefaults } from '@proj-airi/stage-ui/stores/provider-env-bootstrap'
import { useSettings } from '@proj-airi/stage-ui/stores/settings'
import { resolveLessonPageUid } from '@proj-airi/stage-ui/utils/lesson-route'
import { resolveLessonStageModelSelection } from '@proj-airi/stage-ui/utils/lesson-stage-model'
import { resolveLessonStageView } from '@proj-airi/stage-ui/utils/lesson-stage-view'
import { breakpointsTailwind, useBreakpoints, useMouse } from '@vueuse/core'
import { storeToRefs } from 'pinia'
import { computed, onMounted, ref, useTemplateRef, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const lessonStore = useLessonStore()
const lessonChatHistoryStore = useLessonChatHistoryStore()
const { availablePages, selectedPageUid, isConfigured, loading, hasStarted } = storeToRefs(lessonStore)
const settingsStore = useSettings()
const { stageModelRenderer, stageModelSelectedUrl } = storeToRefs(settingsStore)

const route = useRoute()
const router = useRouter()
const positionCursor = useMouse()
const breakpoints = useBreakpoints(breakpointsTailwind)
const isMobile = breakpoints.smaller('md')
const lessonStageView = computed(() => resolveLessonStageView(isMobile.value))
const conversationHistoryExpanded = ref(false)
const lessonDockInset = computed(() => isMobile.value ? '0.75rem' : '1rem')
const lessonSubtitleBottom = computed(() => {
  if (isMobile.value) {
    return '9.25rem'
  }

  return '10.5rem'
})

const backgroundStore = useBackgroundStore()
const { selectedOption, sampledColor } = storeToRefs(backgroundStore)
const backgroundSurface = useTemplateRef<InstanceType<typeof BackgroundProvider>>('backgroundSurface')
const { syncBackgroundTheme } = useBackgroundThemeColor({ backgroundSurface, selectedOption, sampledColor })
let lessonStageRecoveryInFlight = false

const queryPageUid = computed(() => {
  const rawPageUid = route.query.page_uid
  return Array.isArray(rawPageUid) ? rawPageUid[0] : rawPageUid
})

const queryStudentId = computed(() => {
  const rawStudentId = route.query.student_id
  return Array.isArray(rawStudentId) ? rawStudentId[0] : rawStudentId
})

const knownLessonPageUids = computed(() =>
  new Set(availablePages.value.map(page => page.value)),
)

function resolvedLessonPageUid() {
  return resolveLessonPageUid(
    queryPageUid.value?.trim(),
    knownLessonPageUids.value,
    selectedPageUid.value,
  )
}

function resolvedLessonStudentId() {
  return queryStudentId.value?.trim() || lessonStore.studentId.trim() || 'demo-student'
}

function syncRouteStudentId() {
  const nextStudentId = resolvedLessonStudentId()
  if (lessonStore.studentId === nextStudentId) {
    return false
  }

  lessonStore.setStudentId(nextStudentId)
  return true
}

async function replaceLessonPageQuery(pageUid: string) {
  const normalizedPageUid = pageUid.trim()
  const currentPageUid = queryPageUid.value?.trim() || ''

  if (!normalizedPageUid || normalizedPageUid === currentPageUid) {
    return
  }

  await router.replace({
    query: {
      ...route.query,
      page_uid: normalizedPageUid,
    },
  })
}

async function ensureLessonStageModel() {
  if (lessonStageRecoveryInFlight) {
    return
  }

  const nextModelId = resolveLessonStageModelSelection(settingsStore.stageModelSelected)
  const needsRestore = settingsStore.stageModelSelected !== nextModelId
    || stageModelRenderer.value === 'disabled'
    || !stageModelSelectedUrl.value

  if (!needsRestore) {
    return
  }

  lessonStageRecoveryInFlight = true

  try {
    settingsStore.stageModelSelected = nextModelId
    await settingsStore.updateStageModel()
  }
  finally {
    lessonStageRecoveryInFlight = false
  }
}

watch(selectedPageUid, async (pageUid) => {
  if (!pageUid || queryPageUid.value === pageUid) {
    return
  }

  await replaceLessonPageQuery(pageUid)
})

watch(queryPageUid, async (pageUid) => {
  const nextPageUid = resolvedLessonPageUid()
  if (!nextPageUid) {
    return
  }

  if (typeof pageUid !== 'string' || pageUid.trim() !== nextPageUid) {
    await replaceLessonPageQuery(nextPageUid)
  }

  if (nextPageUid === selectedPageUid.value) {
    return
  }

  try {
    await lessonStore.selectLessonPage(nextPageUid, {
      restartIfStarted: hasStarted.value && isConfigured.value,
    })
  }
  catch {
  }
})

watch(queryStudentId, async () => {
  if (!syncRouteStudentId()) {
    return
  }

  lessonStore.resetLessonState({ keepSelectedPage: true })
  await lessonChatHistoryStore.ensureCurrentLessonHistorySession()
  if (
    lessonChatHistoryStore.activeLessonTabWritable
    && !lessonChatHistoryStore.activeHistoryReadOnly
    && isConfigured.value
    && !loading.value
    && !hasStarted.value
  ) {
    try {
      await lessonStore.startLesson(selectedPageUid.value)
    }
    catch {
    }
  }
})

watch([stageModelRenderer, stageModelSelectedUrl], ([renderer, modelUrl]) => {
  if (renderer === 'disabled' || !modelUrl) {
    void ensureLessonStageModel()
  }
}, { immediate: true })

onMounted(async () => {
  await ensureLessonStageModel()
  syncBackgroundTheme()
  await bootstrapPepTutorBackendAuth().catch(() => undefined)
  await bootstrapPepTutorVoiceEnvDefaults().catch(() => undefined)
  void ensureLessonHearingFallbackProvider().catch(() => false)
  void ensureLessonSpeechFallbackProvider().catch(() => false)
  syncRouteStudentId()
  await lessonStore.loadCatalog()

  const nextPageUid = resolvedLessonPageUid()
  if (!nextPageUid) {
    return
  }

  await replaceLessonPageQuery(nextPageUid)

  if (nextPageUid !== selectedPageUid.value) {
    await lessonStore.selectLessonPage(nextPageUid)
  }

  await lessonChatHistoryStore.initialize()

  if (
    lessonChatHistoryStore.activeLessonTabWritable
    && !lessonChatHistoryStore.activeHistoryReadOnly
    && isConfigured.value
    && !loading.value
    && !hasStarted.value
  ) {
    try {
      await lessonStore.startLesson(nextPageUid)
    }
    catch {
    }
  }
})
</script>

<template>
  <BackgroundProvider
    ref="backgroundSurface"
    :background="selectedOption"
    :top-color="sampledColor"
    class="widgets top-widgets"
  >
    <div :class="['relative z-2 flex w-100vw flex-col', isMobile ? 'min-h-100dvh overflow-x-hidden overflow-y-auto' : 'h-100dvh overflow-hidden']">
      <div :class="['relative z-30 w-full gap-2 px-0 py-1 md:px-3 md:py-3']">
        <Header class="hidden md:flex" />
        <MobileHeader class="flex md:hidden" />
      </div>

      <div
        :class="['relative z-10 min-h-0 flex-1 gap-3 px-3 pb-3', isMobile ? 'flex flex-col gap-4 pb-6' : 'grid items-stretch']"
        :style="isMobile ? undefined : { gridTemplateColumns: '304px minmax(0, 1fr) 360px' }"
      >
        <LessonSidebar class="min-h-0 hidden md:flex" />

        <div class="min-h-0 min-w-0 flex flex-1">
          <div
            :class="[
              'relative overflow-hidden rounded-[30px] border border-sky-100/75 bg-[linear-gradient(180deg,rgba(255,255,255,0.62),rgba(240,249,255,0.36))] shadow-[0_35px_120px_-65px_rgba(15,23,42,0.62)] backdrop-blur-md dark:border-neutral-800/70 dark:bg-neutral-950/35 dark:shadow-[0_35px_120px_-55px_rgba(15,23,42,0.95)]',
              isMobile ? 'h-[58dvh] min-h-[30rem] max-h-[36rem] w-full shrink-0' : 'min-h-0 flex-1',
            ]"
          >
            <div class="absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(56,189,248,0.18),transparent_38%),radial-gradient(circle_at_bottom,rgba(255,255,255,0.54),transparent_48%)] dark:bg-[radial-gradient(circle_at_top,rgba(56,189,248,0.14),transparent_38%),radial-gradient(circle_at_bottom,rgba(15,23,42,0.32),transparent_48%)]" />
            <WidgetStage
              class="relative z-10 h-full w-full"
              :paused="false"
              :lesson-safe="true"
              :lesson-speech="true"
              :lesson-chat-runtime="true"
              :focus-at="{
                x: positionCursor.x.value,
                y: positionCursor.y.value,
              }"
              :x-offset="lessonStageView.xOffset"
              :y-offset="lessonStageView.yOffset"
              :scale="lessonStageView.scale"
            />

            <div
              :class="['pointer-events-none absolute inset-x-4 z-10 md:inset-x-6']"
              :style="{ bottom: lessonSubtitleBottom }"
            >
              <LessonSubtitleBar />
            </div>

            <div
              class="absolute inset-x-0 bottom-0 z-20 px-3 pb-3 md:px-4 md:pb-4"
              :style="{ paddingLeft: lessonDockInset, paddingRight: lessonDockInset }"
            >
              <LessonRuntimeChatPanel
                v-model:history-expanded="conversationHistoryExpanded"
                :mobile="isMobile"
                dock-mode
                overlay-mode
              />
            </div>
          </div>
        </div>

        <div :class="['min-h-0', isMobile ? 'relative z-20' : '']">
          <LessonInteractiveArea :mobile="isMobile" />
        </div>
      </div>
    </div>
  </BackgroundProvider>
</template>

<route lang="yaml">
name: LessonScenePage
meta:
  layout: stage
  stageTransition:
    name: bubble-wave-out
</route>
