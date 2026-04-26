<script setup lang="ts">
import type { ChatHistoryItem } from '@proj-airi/stage-ui/types/chat'
import type { ChatSessionRecord } from '@proj-airi/stage-ui/types/chat-session'
import type { LessonRuntimeSnapshot } from '@proj-airi/stage-ui/stores/lesson'

import { ChatHistory } from '@proj-airi/stage-ui/components'
import { useChatOrchestratorStore } from '@proj-airi/stage-ui/stores/chat'
import { useChatSessionStore } from '@proj-airi/stage-ui/stores/chat/session-store'
import { useChatStreamStore } from '@proj-airi/stage-ui/stores/chat/stream-store'
import { useLessonStore } from '@proj-airi/stage-ui/stores/lesson'
import { useLessonAiriRuntimeStore } from '@proj-airi/stage-ui/stores/lesson-airi-runtime'
import { createPepTutorLessonChatProvider, LESSON_CHAT_MODEL } from '@proj-airi/stage-ui/stores/lesson-chat-provider'
import { useHearingStore } from '@proj-airi/stage-ui/stores/modules/hearing'
import { fetchPepTutorBackend } from '@proj-airi/stage-ui/stores/peptutor-backend-auth'
import { useSpeechStore } from '@proj-airi/stage-ui/stores/modules/speech'
import { useDeferredMount } from '@proj-airi/ui'
import { nanoid } from 'nanoid'
import { storeToRefs } from 'pinia'
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'

import ChatArea from './ChatArea.vue'

const props = withDefaults(defineProps<{
  mobile?: boolean
  dockMode?: boolean
  overlayMode?: boolean
}>(), {
  mobile: false,
  dockMode: false,
  overlayMode: false,
})

const historyExpanded = defineModel<boolean>('historyExpanded', { default: true })

const lessonChatProvider = createPepTutorLessonChatProvider()
const lessonStore = useLessonStore()
const lessonAiriRuntime = useLessonAiriRuntimeStore()
const { activeTurn, apiBaseUrl, isConfigured, hasStarted, runtimeState, transcript } = storeToRefs(lessonStore)
const { microphoneStatus, microphoneStatusLabel, autoSendEnabled } = storeToRefs(lessonAiriRuntime)
const { activeSpeechProvider, activeSpeechModel, activeSpeechVoiceId } = storeToRefs(useSpeechStore())
const { activeTranscriptionProvider, activeTranscriptionModel } = storeToRefs(useHearingStore())
const { isReady } = useDeferredMount()
const { sending } = storeToRefs(useChatOrchestratorStore())
const chatSessionStore = useChatSessionStore()
const { activeSessionId, messages } = storeToRefs(chatSessionStore)
const { streamingMessage } = storeToRefs(useChatStreamStore())

const isLoading = ref(true)
const syncedPageUid = ref('')
const syncedStartTurnKey = ref('')
const lessonRuntimeSystemMessageId = 'peptutor-lesson-runtime-system'
const lessonSessionSnapshotStoragePrefix = 'peptutor/lesson/chat-session-runtime/v1/'
let lessonChatHistoryFileSyncTimeout: ReturnType<typeof setTimeout> | undefined
let lessonChatHistoryFileSyncQueue = Promise.resolve()
let lessonChatHistoryFilesHydrated = false
const historyMessages = computed(() => messages.value as unknown as ChatHistoryItem[])
const chatDisabled = computed(() => !isConfigured.value || !hasStarted.value)
const visibleConversationMessages = computed(() =>
  historyMessages.value.filter(message => message.role !== 'system'),
)
const conversationTurnCount = computed(() => visibleConversationMessages.value.length)
const panelTitle = computed(() => props.dockMode ? '课堂对话 Dock' : '米粒老师对话区')
const panelSubtitle = computed(() =>
  props.dockMode
    ? '底部主输入区，聊天记录可展开查看完整轮次。'
    : '和老师实时对话。',
)
const rootClasses = computed(() => props.dockMode
  ? [
      props.overlayMode
        ? 'w-full'
        : 'w-full rounded-[30px] border border-sky-100/80 bg-[linear-gradient(180deg,rgba(255,255,255,0.86),rgba(240,249,255,0.72))] p-3.5 shadow-[0_36px_120px_-70px_rgba(15,23,42,0.62)] backdrop-blur-xl',
      props.overlayMode
        ? ''
        : 'dark:border-white/10 dark:bg-[linear-gradient(180deg,rgba(7,12,20,0.95),rgba(10,16,26,0.88))] dark:shadow-[0_36px_120px_-64px_rgba(2,12,27,0.98)]',
    ]
  : [
      'min-h-0 flex-1 overflow-hidden rounded-[28px] border-2 border-solid border-white/50 bg-white/78 p-4 backdrop-blur-xl',
      'dark:border-neutral-800/70 dark:bg-neutral-950/72',
    ])
const historyShellClasses = computed(() => props.dockMode
  ? [
      'rounded-[26px] border border-sky-100/80 bg-[linear-gradient(180deg,rgba(255,255,255,0.82),rgba(240,249,255,0.68))]',
      'dark:border-white/8 dark:bg-[linear-gradient(180deg,rgba(10,15,25,0.94),rgba(6,10,18,0.88))]',
    ]
  : [
      'rounded-[24px] border border-primary-200/20 bg-primary-50/40',
      'dark:border-primary-400/20 dark:bg-primary-950/35',
    ])
const historyHeightClass = computed(() => {
  if (!historyExpanded.value) {
    return 'h-0'
  }

  if (props.dockMode) {
    if (props.overlayMode) {
      return props.mobile ? 'h-[18dvh]' : 'h-[8rem]'
    }
    return props.mobile ? 'h-[30dvh]' : 'h-[17rem]'
  }

  return props.mobile ? 'h-[44dvh]' : 'h-[32rem]'
})
const inputShellClasses = computed(() => props.dockMode
  ? [
      'overflow-hidden rounded-[28px] border border-sky-100/80 bg-white/58',
      'dark:border-white/8 dark:bg-white/4',
    ]
  : [])
const microphoneBadgeClasses = computed(() => {
  switch (microphoneStatus.value) {
    case 'speaking':
      return 'bg-sky-100/95 text-sky-700 dark:bg-sky-500/20 dark:text-sky-100'
    case 'listening':
    case 'ready':
      return 'bg-emerald-100/95 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-100'
    case 'unavailable':
    case 'denied':
      return 'bg-rose-100/95 text-rose-700 dark:bg-rose-500/20 dark:text-rose-100'
    case 'requesting':
      return 'bg-amber-100/95 text-amber-700 dark:bg-amber-500/20 dark:text-amber-100'
    case 'off':
    default:
      return 'bg-neutral-100/90 text-neutral-500 dark:bg-neutral-800/80 dark:text-neutral-300'
  }
})
const speechProviderLabel = computed(() => {
  if (!activeSpeechProvider.value || activeSpeechProvider.value === 'speech-noop')
    return 'TTS 未配置'
  const parts = [activeSpeechProvider.value, activeSpeechModel.value, activeSpeechVoiceId.value].filter(Boolean)
  return `TTS ${parts.join(' · ')}`
})
const hearingProviderLabel = computed(() => {
  if (!activeTranscriptionProvider.value)
    return 'ASR 未配置'
  const parts = [activeTranscriptionProvider.value, activeTranscriptionModel.value].filter(Boolean)
  return `ASR ${parts.join(' · ')}`
})
const lessonChatHistorySyncUrl = computed(() =>
  apiBaseUrl.value ? `${apiBaseUrl.value}/lesson/chat-history/session` : '',
)
const lessonChatHistorySessionsUrl = computed(() =>
  apiBaseUrl.value ? `${apiBaseUrl.value}/lesson/chat-history/sessions` : '',
)
const lessonChatHistoryFileSyncEnabled = computed(() =>
  import.meta.env.MODE !== 'test' && Boolean(apiBaseUrl.value),
)
const lessonRuntimeSystemPrompt = computed(() => [
  'You are the PepTutor classroom teacher inside AIRI.',
  'Teach the current PEP Grade 5-6 English textbook page in short spoken turns.',
  'Use the lesson backend state as the source of truth for task flow, correction depth, and page progress.',
  'Keep AIRI character expression warm, patient, and age-appropriate.',
  'When the learner answers by voice, treat the transcribed text as the student answer and continue naturally.',
].join('\n'))
const placeholder = computed(() =>
  hasStarted.value
    ? '说话或输入回答'
    : '先点击开始上课',
)

onMounted(async () => {
  try {
    await chatSessionStore.initialize()
    await hydrateLessonChatHistoryFiles()
    queueLessonChatHistoryFileSync()
  }
  catch (error) {
    console.error('[LessonRuntimeChatPanel] Failed to initialize chat session store:', error)
  }
})

onUnmounted(() => {
  if (lessonChatHistoryFileSyncTimeout) {
    clearTimeout(lessonChatHistoryFileSyncTimeout)
    lessonChatHistoryFileSyncTimeout = undefined
  }
})

function cloneJson<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

function writeLessonHistoryRuntimeSnapshot(sessionId: string, snapshot: unknown) {
  if (typeof localStorage === 'undefined' || !sessionId) {
    return
  }

  const normalizedSnapshot = snapshot as LessonRuntimeSnapshot | null | undefined
  if (!normalizedSnapshot || normalizedSnapshot.version !== 1) {
    return
  }

  try {
    localStorage.setItem(
      `${lessonSessionSnapshotStoragePrefix}${sessionId}`,
      JSON.stringify(normalizedSnapshot),
    )
  }
  catch {
  }
}

function lessonChatHistoryRecordFromPayload(payload: unknown): ChatSessionRecord | null {
  if (!payload || typeof payload !== 'object') {
    return null
  }

  const historyPayload = payload as {
    format?: unknown
    metadata?: Record<string, unknown>
    messages?: unknown
  }
  const metadata = historyPayload.metadata
  if (historyPayload.format !== 'peptutor-chat-history:v1' || !metadata || !Array.isArray(historyPayload.messages)) {
    return null
  }

  const sessionId = typeof metadata.session_id === 'string' ? metadata.session_id.trim() : ''
  if (!sessionId) {
    return null
  }

  return {
    meta: {
      sessionId,
      userId: typeof metadata.user_id === 'string' && metadata.user_id.trim() ? metadata.user_id.trim() : 'local',
      characterId: typeof metadata.character_id === 'string' && metadata.character_id.trim() ? metadata.character_id.trim() : 'lesson',
      title: typeof metadata.title === 'string' && metadata.title.trim() ? metadata.title.trim() : undefined,
      createdAt: typeof metadata.created_at === 'number' ? metadata.created_at : Date.now(),
      updatedAt: typeof metadata.updated_at === 'number' ? metadata.updated_at : Date.now(),
    },
    messages: cloneJson(historyPayload.messages as ChatHistoryItem[]),
  }
}

async function hydrateLessonChatHistoryFiles() {
  if (lessonChatHistoryFilesHydrated || !lessonChatHistoryFileSyncEnabled.value || !lessonChatHistorySessionsUrl.value) {
    return
  }

  lessonChatHistoryFilesHydrated = true
  const response = await fetchPepTutorBackend(
    lessonChatHistorySessionsUrl.value,
    { method: 'GET' },
    { retryUnauthorized: false },
  ).catch(() => undefined)
  if (!response?.ok) {
    return
  }

  const summaries = await response.json().catch(() => []) as Array<{ session_id?: unknown }>
  if (!Array.isArray(summaries)) {
    return
  }

  for (const summary of summaries.slice(0, 100)) {
    const sessionId = typeof summary.session_id === 'string' ? summary.session_id.trim() : ''
    if (!sessionId) {
      continue
    }

    const detailResponse = await fetchPepTutorBackend(
      `${lessonChatHistorySessionsUrl.value}/${encodeURIComponent(sessionId)}`,
      { method: 'GET' },
      { retryUnauthorized: false },
    ).catch(() => undefined)
    if (!detailResponse?.ok) {
      continue
    }

    const payload = await detailResponse.json().catch(() => null) as unknown
    const record = lessonChatHistoryRecordFromPayload(payload)
    if (!record) {
      continue
    }

    await chatSessionStore.upsertSessionRecord(record, { setActive: false })
    if (payload && typeof payload === 'object' && 'runtime_snapshot' in payload) {
      writeLessonHistoryRuntimeSnapshot(record.meta.sessionId, (payload as { runtime_snapshot?: unknown }).runtime_snapshot)
    }
  }
}

function queueLessonChatHistoryFileSync() {
  if (!lessonChatHistoryFileSyncEnabled.value) {
    return
  }

  if (lessonChatHistoryFileSyncTimeout) {
    clearTimeout(lessonChatHistoryFileSyncTimeout)
  }

  lessonChatHistoryFileSyncTimeout = setTimeout(() => {
    lessonChatHistoryFileSyncTimeout = undefined
    lessonChatHistoryFileSyncQueue = lessonChatHistoryFileSyncQueue
      .catch(() => undefined)
      .then(syncLessonChatHistoryFile)
  }, 500)
}

async function syncLessonChatHistoryFile() {
  const sessionId = activeSessionId.value
  const syncUrl = lessonChatHistorySyncUrl.value
  if (!lessonChatHistoryFileSyncEnabled.value || !sessionId || !syncUrl) {
    return
  }

  const meta = chatSessionStore.sessionMetas[sessionId]
  if (!meta) {
    return
  }

  const response = await fetchPepTutorBackend(syncUrl, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      session_id: meta.sessionId,
      user_id: meta.userId || 'local',
      character_id: meta.characterId || 'lesson',
      title: meta.title || null,
      created_at: meta.createdAt,
      updated_at: meta.updatedAt,
      active: sessionId === activeSessionId.value,
      page_uid: lessonStore.selectedPageUid || null,
      messages: cloneJson(messages.value),
      runtime_snapshot: lessonStore.exportRuntimeSnapshot(),
    }),
  }, { retryUnauthorized: false }).catch(() => undefined)

  if (!response?.ok) {
    return
  }
}

watch(
  () => lessonStore.selectedPageUid,
  (pageUid) => {
    const normalizedPageUid = pageUid.trim()
    if (!normalizedPageUid || normalizedPageUid === syncedPageUid.value) {
      return
    }

    syncedPageUid.value = ''
    syncedStartTurnKey.value = ''

    const sessionId = activeSessionId.value
    if (sessionId && !lessonStore.runtimeState) {
      chatSessionStore.cleanupMessages(sessionId)
    }
  },
)

watch(
  () => [
    activeSessionId.value,
    lessonStore.runtimeState?.current_page_uid,
    lessonStore.activeTurn?.turn_label,
    lessonStore.activeTurn?.block_uid,
    lessonStore.activeTurn?.teacher_response,
  ] as const,
  ([sessionId, pageUid, turnLabel, blockUid, teacherResponse]) => {
    const normalizedPageUid = pageUid?.trim()
    const normalizedTeacherResponse = teacherResponse?.trim()
    const turnKey = `${normalizedPageUid}:${turnLabel || ''}:${blockUid || ''}:${normalizedTeacherResponse}`
    if (
      !normalizedPageUid
      || turnLabel !== 'page_entry'
      || !normalizedTeacherResponse
      || !sessionId
      || syncedStartTurnKey.value === turnKey
    ) {
      return
    }

    syncedPageUid.value = normalizedPageUid
    syncedStartTurnKey.value = turnKey
    chatSessionStore.cleanupMessages(sessionId)
    const existingMessages = chatSessionStore.getSessionMessages(sessionId)
    const systemMessages = existingMessages.filter(message =>
      message.role === 'system'
      && message.id !== lessonRuntimeSystemMessageId,
    )
    const lessonSystemMessage: ChatHistoryItem = {
      role: 'system',
      content: lessonRuntimeSystemPrompt.value,
      createdAt: Date.now(),
      id: lessonRuntimeSystemMessageId,
    }
    const assistantMessage: ChatHistoryItem = {
      role: 'assistant',
      content: normalizedTeacherResponse,
      slices: [{ type: 'text', text: normalizedTeacherResponse }],
      tool_results: [],
      createdAt: Date.now(),
      id: nanoid(),
    }
    chatSessionStore.setSessionMessages(sessionId, [...systemMessages, lessonSystemMessage, assistantMessage])
  },
  { immediate: true },
)

watch(
  [activeSessionId, messages, runtimeState, activeTurn, transcript],
  queueLessonChatHistoryFileSync,
  { deep: true, flush: 'post' },
)
</script>

<template>
  <div :class="rootClasses">
    <template v-if="props.overlayMode">
      <ChatArea
        :chat-provider-override="lessonChatProvider"
        :model-override="LESSON_CHAT_MODEL"
        :provider-config-override="{}"
        :disabled="chatDisabled"
        :placeholder="placeholder"
        :auto-send-enabled-override="true"
        :auto-send-delay-override="900"
        :interrupt-playback-on-input="true"
        push-to-talk-hotkey
        compact-mode
      />
    </template>

    <template v-else>
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div class="min-w-0">
        <div class="text-sm font-semibold text-slate-900 dark:text-neutral-100">
          {{ panelTitle }}
        </div>
        <div class="text-xs text-slate-500 dark:text-neutral-400">
          {{ panelSubtitle }}
        </div>
      </div>

      <div class="flex items-center gap-2">
        <button
          v-if="props.dockMode"
          class="h-9 w-9 flex items-center justify-center rounded-full border border-sky-100/90 bg-white/70 text-slate-600 transition hover:bg-sky-50 dark:border-white/12 dark:bg-white/6 dark:text-neutral-100 dark:hover:bg-white/12"
          :aria-label="historyExpanded ? '收起对话记录' : '展开对话记录'"
          :title="historyExpanded ? '收起对话记录' : '展开对话记录'"
          @click="historyExpanded = !historyExpanded"
        >
          <div :class="historyExpanded ? 'i-solar:alt-arrow-down-linear' : 'i-solar:alt-arrow-up-linear'" class="h-4 w-4" />
        </button>

        <div class="rounded-full bg-sky-100/75 px-3 py-1 text-xs font-medium text-slate-600 dark:bg-white/8 dark:text-neutral-100">
          {{ conversationTurnCount }} 条对话
        </div>
        <div
          :class="[
            'rounded-full px-3 py-1 text-xs font-medium',
            hasStarted
              ? 'bg-emerald-100/95 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-100'
              : 'bg-neutral-100/90 text-neutral-500 dark:bg-neutral-800/80 dark:text-neutral-300',
          ]"
        >
          {{ hasStarted ? '已接入' : '未开始' }}
        </div>
      </div>
    </div>

    <div class="mt-3 flex flex-wrap gap-2">
      <div
        :class="[
          'rounded-full px-3 py-1 text-xs font-medium',
          microphoneBadgeClasses,
        ]"
      >
        {{ microphoneStatusLabel }}
      </div>
      <div
        :class="[
          'rounded-full px-3 py-1 text-xs font-medium',
          autoSendEnabled
            ? 'bg-indigo-100/95 text-indigo-700 dark:bg-indigo-500/20 dark:text-indigo-100'
            : 'bg-neutral-100/90 text-neutral-500 dark:bg-neutral-800/80 dark:text-neutral-300',
        ]"
      >
        {{ autoSendEnabled ? '语音自动发送' : '语音手动发送' }}
      </div>
      <div class="rounded-full bg-sky-100/75 px-3 py-1 text-xs font-medium text-slate-600 dark:bg-white/8 dark:text-neutral-200">
        {{ speechProviderLabel }}
      </div>
      <div class="rounded-full bg-sky-100/75 px-3 py-1 text-xs font-medium text-slate-600 dark:bg-white/8 dark:text-neutral-200">
        {{ hearingProviderLabel }}
      </div>
    </div>

    <div
      v-if="historyExpanded"
      :class="[historyHeightClass, 'mt-3 min-h-0 overflow-hidden transition-[height] duration-250']"
    >
      <div :class="[historyShellClasses, 'relative flex h-full min-h-0 flex-col overflow-hidden']">
        <div
          v-if="isLoading"
          absolute left-0 top-0 h-1 w-full overflow-hidden rounded-t-xl
          class="bg-primary-500/20"
        >
          <div h-full w="1/3" origin-left bg-primary-500 class="animate-scan" />
        </div>

        <div class="flex items-center justify-between gap-3 border-b border-sky-100/80 px-4 py-3 dark:border-white/8">
          <div>
            <div class="text-sm font-semibold text-slate-900 dark:text-white">
              聊天记录
            </div>
            <div class="text-xs text-slate-500 dark:text-neutral-400">
              AIRI runtime 与 lesson turn 的合并对话视图
            </div>
          </div>
          <div class="rounded-full bg-sky-100/75 px-3 py-1 text-[11px] font-medium text-slate-600 dark:bg-white/8 dark:text-neutral-200">
            {{ historyExpanded ? '展开中' : '已收起' }}
          </div>
        </div>

        <div class="relative flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg px-2 py-3 md:px-0">
          <ChatHistory
            v-if="isReady"
            :messages="historyMessages"
            :sending="sending"
            :streaming-message="streamingMessage"
            h-full
            :variant="props.mobile ? 'mobile' : 'desktop'"
            @vue:mounted="isLoading = false"
          />
        </div>
      </div>
    </div>

    <div :class="['mt-3', inputShellClasses]">
      <div
        v-if="props.dockMode && !historyExpanded"
        class="flex items-center justify-between gap-3 border-b border-sky-100/80 px-4 py-2 text-xs text-slate-500 dark:border-white/8 dark:text-neutral-300"
      >
        <span>聊天记录已收起，输入框仍然可用。</span>
        <button
          class="rounded-full bg-sky-100/75 px-3 py-1 font-medium text-slate-700 transition hover:bg-white dark:bg-white/8 dark:text-neutral-100 dark:hover:bg-white/12"
          aria-label="展开对话记录"
          title="展开对话记录"
          @click="historyExpanded = true"
        >
          展开记录
        </button>
      </div>

      <ChatArea
        :chat-provider-override="lessonChatProvider"
        :model-override="LESSON_CHAT_MODEL"
        :provider-config-override="{}"
        :disabled="chatDisabled"
        :placeholder="placeholder"
        :auto-send-enabled-override="true"
        :auto-send-delay-override="900"
        :interrupt-playback-on-input="true"
        push-to-talk-hotkey
        :compact-mode="props.overlayMode"
      />
    </div>
    </template>
  </div>
</template>

<style scoped>
@keyframes scan {
  0% {
    transform: translateX(-100%);
  }
  100% {
    transform: translateX(400%);
  }
}

.animate-scan {
  animation: scan 2s infinite linear;
}
</style>
