<script setup lang="ts">
import type { ChatHistoryItem } from '@proj-airi/stage-ui/types/chat'
import type { LessonRuntimeSnapshot } from '@proj-airi/stage-ui/stores/lesson'

import { useChatSessionStore } from '@proj-airi/stage-ui/stores/chat/session-store'
import { useChatStreamStore } from '@proj-airi/stage-ui/stores/chat/stream-store'
import { useLessonStore } from '@proj-airi/stage-ui/stores/lesson'
import { useLessonAiriRuntimeStore } from '@proj-airi/stage-ui/stores/lesson-airi-runtime'
import { useHearingStore } from '@proj-airi/stage-ui/stores/modules/hearing'
import { useSpeechStore } from '@proj-airi/stage-ui/stores/modules/speech'
import { storeToRefs } from 'pinia'
import { computed, nextTick, onMounted, ref, watch } from 'vue'

const lessonStore = useLessonStore()
const { currentPageTitle, selectedPageUid, loading, runtimeState, activeTurn, transcript, isConfigured } = storeToRefs(lessonStore)
const lessonAiriRuntime = useLessonAiriRuntimeStore()
const {
  microphoneEnabled,
  microphoneReady,
  microphoneStatusLabel,
  microphoneInputDeviceLabel,
  microphonePermissionState,
  microphonePermissionError,
  hearingListening,
  hearingConfigured,
  supportsStreamInput,
  autoSendEnabled,
  autoSendDelay,
  teacherSpeaking,
  inputVolumeLevel,
  classroomState,
  liveTranscriptText,
  currentSpeechStyle,
  currentMouthIntensity,
  currentInterruptPolicy,
  currentPerformancePlan,
} = storeToRefs(lessonAiriRuntime)
const { activeTranscriptionProvider } = storeToRefs(useHearingStore())
const { activeSpeechProvider } = storeToRefs(useSpeechStore())

const chatSessionStore = useChatSessionStore()
const { activeSessionId, currentCharacterSessionMetas, messages } = storeToRefs(chatSessionStore)
const { streamingMessage } = storeToRefs(useChatStreamStore())
const sidebarChatScrollRef = ref<HTMLElement>()
const historyPanelOpen = ref(false)
const lessonSessionSwitching = ref(false)

const lessonSessionSnapshotStoragePrefix = 'peptutor/lesson/chat-session-runtime/v1/'

const historyMessages = computed(() =>
  (messages.value as unknown as ChatHistoryItem[]).filter(message => message.role !== 'system'),
)
const conversationCountLabel = computed(() => `${historyMessages.value.length} 条对话`)
const sidebarMessages = computed(() => {
  const normalized = historyMessages.value
    .map((message, index) => ({
      id: message.id || `${message.role}:${message.createdAt || index}`,
      role: message.role,
      text: resolveMessageText(message),
      createdAt: message.createdAt,
    }))
    .filter(message => (message.role === 'assistant' || message.role === 'user' || message.role === 'error') && message.text)

  const streamingText = streamingMessage.value ? resolveMessageText(streamingMessage.value as ChatHistoryItem) : ''
  if (streamingText) {
    normalized.push({
      id: 'streaming-message',
      role: 'assistant',
      text: streamingText,
      createdAt: Date.now(),
    })
  }

  return normalized
})
const latestAssistantPreview = computed(() =>
  [...sidebarMessages.value].reverse().find(message => message.role === 'assistant')?.text || '老师开始后，对话记录会显示在这里。',
)
const historySessionRows = computed(() =>
  currentCharacterSessionMetas.value.map(meta => ({
    id: meta.sessionId,
    title: resolveSessionTitle(meta.sessionId, meta.title),
    updatedAt: formatSessionTime(meta.updatedAt),
    active: meta.sessionId === activeSessionId.value,
  })),
)
const browserContextLabel = computed(() => {
  if (typeof window === 'undefined') {
    return '未知'
  }

  return window.isSecureContext ? '安全上下文' : '非安全上下文'
})
const permissionStateLabel = computed(() => {
  switch (microphonePermissionState.value) {
    case 'requesting':
      return '请求中'
    case 'granted':
      return '已授权'
    case 'denied':
      return '已拒绝'
    case 'unavailable':
      return '不可用'
    case 'unknown':
    default:
      return '未授权'
  }
})
const sidebarRuntimeMetaLabel = computed(() => {
  if (microphonePermissionError.value) {
    return microphoneInputDeviceLabel.value || '未选择输入设备'
  }

  return microphoneStatusLabel.value
})
const hearingProviderLabel = computed(() => {
  if (!hearingConfigured.value || !activeTranscriptionProvider.value) {
    return '未配置'
  }

  return activeTranscriptionProvider.value
})
const speechProviderLabel = computed(() => {
  if (!activeSpeechProvider.value || activeSpeechProvider.value === 'speech-noop') {
    return '未配置'
  }

  return activeSpeechProvider.value
})
const autoSendLabel = computed(() =>
  autoSendEnabled.value ? `${autoSendDelay.value}ms` : '关闭',
)
const speechChainFacts = computed(() => [
  {
    key: 'secure_context',
    label: '浏览器',
    value: browserContextLabel.value,
  },
  {
    key: 'permission',
    label: '权限',
    value: permissionStateLabel.value,
  },
  {
    key: 'stream_input',
    label: '流式',
    value: supportsStreamInput.value ? '支持' : '不支持',
  },
  {
    key: 'auto_send',
    label: '自动发送',
    value: autoSendLabel.value,
  },
  {
    key: 'asr',
    label: 'ASR',
    value: hearingProviderLabel.value,
  },
  {
    key: 'tts',
    label: 'TTS',
    value: speechProviderLabel.value,
  },
  {
    key: 'speech_style',
    label: '语气',
    value: currentSpeechStyle.value,
  },
  {
    key: 'mouth_intensity',
    label: '嘴型',
    value: currentMouthIntensity.value.toFixed(2),
  },
  {
    key: 'interrupt_policy',
    label: '打断',
    value: currentInterruptPolicy.value,
  },
  {
    key: 'motion',
    label: '动作',
    value: currentPerformancePlan.value?.motion || '待命',
  },
  {
    key: 'expression',
    label: '表情',
    value: currentPerformancePlan.value?.expression || 'neutral',
  },
  {
    key: 'performance_source',
    label: '表现层',
    value: currentPerformancePlan.value?.performanceSource || '未收到',
  },
])
const toolbarItems = [
  { key: 'settings', icon: 'i-solar:settings-linear', label: '设置', href: '/settings/system/general' },
  { key: 'people', icon: 'i-solar:users-group-rounded-linear', label: '学生' },
  { key: 'history', icon: 'i-solar:history-line-duotone', label: '历史' },
  { key: 'plus', icon: 'i-solar:add-circle-linear', label: '新建' },
  { key: 'layers', icon: 'i-solar:layers-minimalistic-linear', label: '上下文' },
]

function scrollSidebarChatToBottom() {
  requestAnimationFrame(() => {
    requestAnimationFrame(async () => {
      await nextTick()
      if (!sidebarChatScrollRef.value) {
        return
      }

      sidebarChatScrollRef.value.scrollTop = sidebarChatScrollRef.value.scrollHeight
    })
  })
}

watch(sidebarMessages, scrollSidebarChatToBottom, { deep: true, flush: 'post' })
onMounted(scrollSidebarChatToBottom)

function lessonSessionSnapshotKey(sessionId: string) {
  return `${lessonSessionSnapshotStoragePrefix}${sessionId}`
}

function readLessonSessionSnapshot(sessionId: string): LessonRuntimeSnapshot | null {
  if (typeof localStorage === 'undefined' || !sessionId) {
    return null
  }

  try {
    const raw = localStorage.getItem(lessonSessionSnapshotKey(sessionId))
    if (!raw) {
      return null
    }
    const parsed = JSON.parse(raw) as LessonRuntimeSnapshot
    return parsed?.version === 1 ? parsed : null
  }
  catch {
    return null
  }
}

function writeLessonSessionSnapshot(sessionId: string, snapshot: LessonRuntimeSnapshot) {
  if (typeof localStorage === 'undefined' || !sessionId) {
    return
  }

  try {
    localStorage.setItem(lessonSessionSnapshotKey(sessionId), JSON.stringify(snapshot))
  }
  catch {
  }
}

function persistActiveLessonRuntimeSnapshot() {
  if (lessonSessionSwitching.value || !activeSessionId.value) {
    return
  }

  writeLessonSessionSnapshot(activeSessionId.value, lessonStore.exportRuntimeSnapshot())
}

function resolveSessionTitle(sessionId: string, title?: string) {
  const explicitTitle = title?.trim()
  if (explicitTitle) {
    return explicitTitle
  }

  const previewText = (chatSessionStore.sessionMessages[sessionId] || [])
    .find(message => message.role !== 'system' && resolveMessageText(message).trim())

  const resolvedText = previewText ? resolveMessageText(previewText).replace(/\s+/g, ' ').trim() : ''
  if (!resolvedText) {
    return '新课堂对话'
  }

  return resolvedText.length > 22 ? `${resolvedText.slice(0, 22)}...` : resolvedText
}

function formatSessionTime(updatedAt: number) {
  try {
    return new Intl.DateTimeFormat('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    }).format(new Date(updatedAt))
  }
  catch {
    return ''
  }
}

function newSessionTitle() {
  const pageTitle = currentPageTitle.value?.trim() || selectedPageUid.value || '课堂'
  return `${pageTitle} · ${formatSessionTime(Date.now())}`
}

async function startCurrentLessonSilently() {
  if (!isConfigured.value || loading.value || !selectedPageUid.value) {
    return
  }

  await lessonStore.startLesson(selectedPageUid.value, { replayTeacher: false })
}

async function createNewLessonSession() {
  persistActiveLessonRuntimeSnapshot()
  lessonSessionSwitching.value = true
  try {
    lessonStore.resetLessonState({ keepSelectedPage: true })
    await chatSessionStore.createCurrentSession({ title: newSessionTitle() })
    await startCurrentLessonSilently()
    historyPanelOpen.value = false
  }
  finally {
    lessonSessionSwitching.value = false
    persistActiveLessonRuntimeSnapshot()
    scrollSidebarChatToBottom()
  }
}

async function selectLessonHistorySession(sessionId: string) {
  if (!sessionId) {
    return
  }

  if (sessionId === activeSessionId.value) {
    historyPanelOpen.value = false
    scrollSidebarChatToBottom()
    return
  }

  persistActiveLessonRuntimeSnapshot()
  lessonSessionSwitching.value = true
  try {
    chatSessionStore.setActiveSession(sessionId)
    await chatSessionStore.loadSession(sessionId)

    const snapshot = readLessonSessionSnapshot(sessionId)
    if (snapshot) {
      lessonStore.restoreRuntimeSnapshot(snapshot)
    }
    else {
      lessonStore.resetLessonState({ keepSelectedPage: true })
      await startCurrentLessonSilently()
    }

    historyPanelOpen.value = false
  }
  finally {
    lessonSessionSwitching.value = false
    persistActiveLessonRuntimeSnapshot()
    scrollSidebarChatToBottom()
  }
}

function handleToolbarButton(item: { key: string }) {
  if (item.key === 'history') {
    historyPanelOpen.value = !historyPanelOpen.value
    return
  }

  if (item.key === 'plus') {
    void createNewLessonSession()
  }
}

watch(
  [activeSessionId, selectedPageUid, runtimeState, activeTurn, transcript],
  persistActiveLessonRuntimeSnapshot,
  { deep: true, flush: 'post' },
)

const sidebarRuntimeStatus = computed(() => {
  if (microphonePermissionState.value === 'requesting') {
    return {
      label: '接入中',
      detail: '正在向浏览器请求麦克风，并尝试连接当前输入设备。',
      classes: 'bg-sky-100 text-sky-700 ring-sky-200 dark:bg-sky-400/14 dark:text-sky-100 dark:ring-sky-300/18',
    }
  }

  if (microphonePermissionError.value) {
    return {
      label: '接入失败',
      detail: microphonePermissionError.value,
      classes: 'bg-rose-100 text-rose-700 ring-rose-200 dark:bg-rose-400/14 dark:text-rose-100 dark:ring-rose-300/18',
    }
  }

  if (teacherSpeaking.value) {
    return {
      label: '说话中',
      detail: '老师正在播报当前页面内容。',
      classes: 'bg-cyan-100 text-cyan-700 ring-cyan-200 dark:bg-cyan-400/14 dark:text-cyan-100 dark:ring-cyan-300/18',
    }
  }

  if (loading.value) {
    return {
      label: '思考中',
      detail: '正在等待 lesson backend 返回下一句。',
      classes: 'bg-amber-100 text-amber-700 ring-amber-200 dark:bg-amber-400/14 dark:text-amber-100 dark:ring-amber-300/18',
    }
  }

  if (hearingListening.value) {
    return {
      label: '聆听中',
      detail: '学生说话时会实时更新下面的转写。',
      classes: 'bg-emerald-100 text-emerald-700 ring-emerald-200 dark:bg-emerald-400/14 dark:text-emerald-100 dark:ring-emerald-300/18',
    }
  }

  if (microphoneEnabled.value && microphoneReady.value) {
    return {
      label: '待命中',
      detail: '麦克风已经接通，等待学生开口。',
      classes: 'bg-sky-100 text-sky-700 ring-sky-200 dark:bg-sky-400/14 dark:text-sky-100 dark:ring-sky-300/18',
    }
  }

  return {
    label: '未接通',
    detail: '当前还没有开始实时听写。',
    classes: 'bg-slate-100 text-slate-600 ring-slate-200 dark:bg-white/10 dark:text-neutral-100 dark:ring-white/10',
  }
})
const visibleAiriState = computed(() => {
  if (classroomState.value === 'interrupted') {
    return {
      label: '被打断',
      detail: '已停止播报，等待学生问题或下一轮输入。',
      classes: 'bg-rose-100 text-rose-700 ring-rose-200 dark:bg-rose-400/14 dark:text-rose-100 dark:ring-rose-300/18',
    }
  }

  if (teacherSpeaking.value || classroomState.value === 'teacher_speaking') {
    return {
      label: '老师说话',
      detail: '按后端表现计划播报当前回复。',
      classes: 'bg-cyan-100 text-cyan-700 ring-cyan-200 dark:bg-cyan-400/14 dark:text-cyan-100 dark:ring-cyan-300/18',
    }
  }

  if (classroomState.value === 'learner_speaking' || (hearingListening.value && inputVolumeLevel.value >= 8)) {
    return {
      label: '学生说话',
      detail: '正在接收学生声音并更新转写。',
      classes: 'bg-emerald-100 text-emerald-700 ring-emerald-200 dark:bg-emerald-400/14 dark:text-emerald-100 dark:ring-emerald-300/18',
    }
  }

  if (loading.value || classroomState.value === 'thinking') {
    return {
      label: '思考中',
      detail: '等待 lesson backend 返回下一句。',
      classes: 'bg-amber-100 text-amber-700 ring-amber-200 dark:bg-amber-400/14 dark:text-amber-100 dark:ring-amber-300/18',
    }
  }

  if (classroomState.value === 'listening' || hearingListening.value) {
    return {
      label: '聆听中',
      detail: '等待学生开口。',
      classes: 'bg-sky-100 text-sky-700 ring-sky-200 dark:bg-sky-400/14 dark:text-sky-100 dark:ring-sky-300/18',
    }
  }

  if (microphoneEnabled.value && microphoneReady.value) {
    return {
      label: '待命中',
      detail: '麦克风已接通，等待课堂输入。',
      classes: 'bg-slate-100 text-slate-600 ring-slate-200 dark:bg-white/10 dark:text-neutral-100 dark:ring-white/10',
    }
  }

  return {
    label: '未接通',
    detail: '实时听写尚未开始。',
    classes: 'bg-slate-100 text-slate-600 ring-slate-200 dark:bg-white/10 dark:text-neutral-100 dark:ring-white/10',
  }
})
const visibleTeachingStance = computed(() => {
  const action = currentPerformancePlan.value?.teachingAction || ''
  const evaluation = currentPerformancePlan.value?.evaluation || ''

  if (['incorrect', 'partially_correct', 'unclear'].includes(evaluation)) {
    return {
      label: '纠错中',
      detail: '短提示、示范或重复操练。',
      classes: 'bg-amber-100 text-amber-700 ring-amber-200 dark:bg-amber-400/14 dark:text-amber-100 dark:ring-amber-300/18',
    }
  }

  if (['correct', 'acceptable'].includes(evaluation) || ['confirm', 'complete'].includes(action)) {
    return {
      label: '鼓励推进',
      detail: '确认答案并推动下一步。',
      classes: 'bg-emerald-100 text-emerald-700 ring-emerald-200 dark:bg-emerald-400/14 dark:text-emerald-100 dark:ring-emerald-300/18',
    }
  }

  if (['page_intro', 'hint', 'model', 'repeat_drill', 'probe'].includes(action)) {
    return {
      label: '鼓励支架',
      detail: '给出可跟读的小步提示。',
      classes: 'bg-emerald-100 text-emerald-700 ring-emerald-200 dark:bg-emerald-400/14 dark:text-emerald-100 dark:ring-emerald-300/18',
    }
  }

  if (action === 'redirect') {
    return {
      label: '回主线',
      detail: '温和拉回当前学习任务。',
      classes: 'bg-sky-100 text-sky-700 ring-sky-200 dark:bg-sky-400/14 dark:text-sky-100 dark:ring-sky-300/18',
    }
  }

  if (action === 'explain') {
    return {
      label: '解释中',
      detail: '回答知识问题但保持课堂节奏。',
      classes: 'bg-cyan-100 text-cyan-700 ring-cyan-200 dark:bg-cyan-400/14 dark:text-cyan-100 dark:ring-cyan-300/18',
    }
  }

  return {
    label: currentPerformancePlan.value ? '引导中' : '等待计划',
    detail: currentPerformancePlan.value ? '按当前教学动作引导学生。' : '还没有收到后端表现计划。',
    classes: 'bg-slate-100 text-slate-600 ring-slate-200 dark:bg-white/10 dark:text-neutral-100 dark:ring-white/10',
  }
})
const visiblePerformanceFacts = computed(() => [
  {
    key: 'voice_pacing',
    label: '节奏',
    value: currentSpeechStyle.value,
  },
  {
    key: 'mouth_intensity',
    label: '嘴型',
    value: currentMouthIntensity.value.toFixed(2),
  },
  {
    key: 'motion',
    label: '动作',
    value: currentPerformancePlan.value?.motion || '待命',
  },
  {
    key: 'expression',
    label: '表情',
    value: currentPerformancePlan.value?.expression || 'neutral',
  },
  {
    key: 'interrupt_policy',
    label: '打断',
    value: currentInterruptPolicy.value,
  },
])

function resolveMessageText(message: ChatHistoryItem): string {
  if ('slices' in message && Array.isArray(message.slices) && message.slices.length > 0) {
    return message.slices
      .filter(slice => slice.type === 'text')
      .map(slice => slice.text)
      .join('')
      .trim()
  }

  const content = message.content
  if (typeof content === 'string') {
    return content.trim()
  }

  if (Array.isArray(content)) {
    return content
      .map((part) => {
        if (typeof part === 'string') {
          return part
        }
        if (part && typeof part === 'object' && 'text' in part && typeof part.text === 'string') {
          return part.text
        }
        return ''
      })
      .filter(Boolean)
      .join('\n')
      .trim()
  }

  return ''
}
</script>

<template>
  <aside
    class="h-full min-h-0 flex flex-col overflow-hidden border border-sky-100/80 rounded-[26px] bg-[linear-gradient(180deg,rgba(255,255,255,0.92),rgba(237,248,255,0.78))] p-3 text-slate-900 shadow-[0_30px_90px_-58px_rgba(14,116,144,0.55)] backdrop-blur-xl dark:border-white/10 dark:bg-[linear-gradient(180deg,rgba(19,22,30,0.98),rgba(9,12,18,0.96))] dark:text-neutral-100 dark:shadow-[0_30px_90px_-44px_rgba(2,8,23,0.82)]"
  >
    <div class="flex items-center justify-between gap-2 px-1 pb-2">
      <div class="flex items-center gap-1.5">
        <template v-for="item in toolbarItems" :key="item.key">
          <a
            v-if="item.href"
            :href="item.href"
            class="h-8 w-8 flex items-center justify-center rounded-full text-slate-500 transition hover:bg-sky-100/75 dark:text-neutral-300 hover:text-slate-900 dark:hover:bg-white/8 dark:hover:text-white"
            :aria-label="item.label"
            :title="item.label"
          >
            <div :class="[item.icon, 'h-4.5 w-4.5']" />
          </a>
          <button
            v-else
            :class="[
              'h-8 w-8 flex items-center justify-center rounded-full text-slate-500 transition hover:bg-sky-100/75 dark:text-neutral-300 hover:text-slate-900 dark:hover:bg-white/8 dark:hover:text-white',
              item.key === 'history' && historyPanelOpen ? 'bg-sky-100/75 text-slate-900 dark:bg-white/10 dark:text-white' : '',
            ]"
            :aria-label="item.label"
            :title="item.label"
            type="button"
            @click="handleToolbarButton(item)"
          >
            <div :class="[item.icon, 'h-4.5 w-4.5']" />
          </button>
        </template>
      </div>

      <div class="rounded-full bg-emerald-400 px-3 py-1 text-[11px] text-emerald-950 font-semibold shadow-[0_12px_24px_-16px_rgba(34,197,94,0.85)]">
        已连接
      </div>
    </div>

    <div
      v-if="historyPanelOpen"
      class="mb-2 shrink-0 overflow-hidden border border-sky-100/90 rounded-[18px] bg-white/72 shadow-[0_18px_44px_-36px_rgba(14,116,144,0.55)] dark:border-white/10 dark:bg-black/32"
    >
      <div class="flex items-center justify-between gap-2 border-b border-sky-100/80 px-3 py-2 dark:border-white/8">
        <div class="min-w-0">
          <div class="text-xs text-slate-900 font-semibold dark:text-white">
            历史对话
          </div>
          <div class="truncate text-[11px] text-slate-500 dark:text-neutral-400">
            切换后会恢复对应课堂状态
          </div>
        </div>
        <button
          class="h-7 w-7 flex shrink-0 items-center justify-center rounded-full bg-sky-100/75 text-slate-600 transition hover:bg-sky-50 dark:bg-white/8 dark:text-neutral-100 dark:hover:bg-white/12"
          aria-label="新建课堂对话"
          title="新建课堂对话"
          type="button"
          @click="void createNewLessonSession()"
        >
          <div class="i-solar:add-circle-linear h-4 w-4" />
        </button>
      </div>

      <div class="max-h-58 overflow-y-auto p-2">
        <button
          v-for="session in historySessionRows"
          :key="session.id"
          :class="[
            'mb-1 w-full min-w-0 rounded-[14px] px-3 py-2 text-left transition last:mb-0',
            session.active
              ? 'bg-sky-100/90 text-slate-900 ring-1 ring-inset ring-sky-200/80 dark:bg-white/12 dark:text-white dark:ring-white/12'
              : 'text-slate-700 hover:bg-sky-50/90 dark:text-neutral-200 dark:hover:bg-white/8',
          ]"
          type="button"
          @click="void selectLessonHistorySession(session.id)"
        >
          <div class="flex items-center justify-between gap-2">
            <span class="truncate text-xs font-semibold">{{ session.title }}</span>
            <span class="shrink-0 text-[10px] text-slate-400 dark:text-neutral-500">{{ session.updatedAt }}</span>
          </div>
          <div class="mt-1 truncate text-[11px] text-slate-500 dark:text-neutral-400">
            {{ session.active ? '当前对话' : '点击恢复并继续' }}
          </div>
        </button>

        <div
          v-if="historySessionRows.length === 0"
          class="rounded-[14px] border border-dashed border-sky-100/90 px-3 py-3 text-xs text-slate-500 dark:border-white/10 dark:text-neutral-400"
        >
          还没有历史对话。
        </div>
      </div>
    </div>

    <div class="mt-1 min-h-0 flex-1 overflow-hidden border border-sky-100/90 rounded-[20px] bg-white/52 dark:border-white/8 dark:bg-black/18">
      <div class="flex items-center justify-between border-b border-sky-100/90 px-3 py-2 dark:border-white/8">
        <div>
          <div class="text-sm text-slate-900 font-semibold dark:text-white">
            聊天记录
          </div>
          <div class="text-[11px] text-slate-500 dark:text-neutral-400">
            米粒老师与学生的课堂轮次
          </div>
        </div>
        <div class="rounded-full bg-sky-100/75 px-2.5 py-1 text-[11px] text-slate-600 font-medium dark:bg-white/8 dark:text-neutral-300">
          {{ conversationCountLabel }}
        </div>
      </div>

      <div ref="sidebarChatScrollRef" class="h-full overflow-y-auto px-2.5 py-3 pb-16">
        <div
          v-if="sidebarMessages.length === 0"
          class="border border-sky-100/90 rounded-[18px] border-dashed bg-white/62 px-3 py-4 text-sm text-slate-500 leading-6 dark:border-white/10 dark:bg-white/5 dark:text-neutral-300"
        >
          {{ latestAssistantPreview }}
        </div>

        <div v-else class="flex flex-col gap-3">
          <div
            v-for="message in sidebarMessages"
            :key="message.id"
            :class="[
              'flex items-end gap-2',
              message.role === 'user' ? 'justify-end' : 'justify-start',
            ]"
          >
            <div
              v-if="message.role !== 'user'"
              class="h-7 w-7 shrink-0 overflow-hidden rounded-full bg-[linear-gradient(135deg,rgba(56,189,248,0.24),rgba(14,165,233,0.08))] ring-1 ring-sky-100/90 dark:ring-white/10"
            >
              <div class="h-full w-full flex items-center justify-center text-[11px] text-cyan-700 font-bold dark:text-cyan-100">
                米
              </div>
            </div>

            <div
              :class="[
                'max-w-[13.5rem] whitespace-pre-wrap break-words rounded-[18px] px-3 py-2.5 text-sm leading-5 shadow-[0_16px_34px_-28px_rgba(0,0,0,0.85)]',
                message.role === 'user'
                  ? 'rounded-br-md bg-emerald-100 text-emerald-950 ring-1 ring-inset ring-emerald-200/80 dark:bg-neutral-600 dark:text-white dark:ring-transparent'
                  : message.role === 'error'
                    ? 'rounded-bl-md bg-rose-50 text-rose-700 ring-1 ring-inset ring-rose-200 dark:bg-rose-500/18 dark:text-rose-100 dark:ring-rose-300/18'
                    : 'rounded-bl-md bg-white/88 text-slate-800 ring-1 ring-inset ring-sky-100/90 dark:bg-neutral-600/72 dark:text-neutral-50 dark:ring-transparent',
              ]"
            >
              {{ message.text }}
            </div>

            <div
              v-if="message.role === 'user'"
              class="h-8 w-8 flex shrink-0 items-center justify-center rounded-full bg-emerald-400 text-sm text-emerald-950 font-bold"
            >
              M
            </div>
          </div>
        </div>
      </div>
    </div>

    <div
      class="mt-3 shrink-0 border border-sky-100/90 rounded-[20px] bg-white/62 p-3 shadow-[0_18px_44px_-34px_rgba(14,116,144,0.55)] dark:border-white/8 dark:bg-black/20"
      data-testid="lesson-airi-visible-closure"
    >
      <div class="flex items-start justify-between gap-3">
        <div class="min-w-0">
          <div class="text-[10px] text-slate-400 font-semibold tracking-[0.14em] uppercase dark:text-neutral-500">
            米粒老师状态
          </div>
          <div
            class="mt-1 truncate text-sm text-slate-900 font-semibold dark:text-white"
            data-testid="lesson-airi-visible-state"
          >
            {{ visibleAiriState.label }}
          </div>
          <div
            class="line-clamp-2 mt-0.5 text-[11px] text-slate-500 leading-4 dark:text-neutral-400"
            data-testid="lesson-airi-visible-state-detail"
          >
            {{ visibleAiriState.detail }}
          </div>
        </div>
        <div
          :class="[
            'shrink-0 rounded-full px-2.5 py-1 text-[11px] font-semibold ring-1 ring-inset',
            visibleAiriState.classes,
          ]"
        >
          {{ visibleAiriState.label }}
        </div>
      </div>

      <div class="mt-3 flex items-start justify-between gap-3 border-t border-sky-100/80 pt-3 dark:border-white/8">
        <div class="min-w-0">
          <div class="text-[10px] text-slate-400 font-semibold tracking-[0.14em] uppercase dark:text-neutral-500">
            教学姿态
          </div>
          <div
            class="mt-1 truncate text-sm text-slate-900 font-semibold dark:text-white"
            data-testid="lesson-airi-teaching-stance"
          >
            {{ visibleTeachingStance.label }}
          </div>
          <div
            class="line-clamp-2 mt-0.5 text-[11px] text-slate-500 leading-4 dark:text-neutral-400"
            data-testid="lesson-airi-teaching-stance-detail"
          >
            {{ visibleTeachingStance.detail }}
          </div>
        </div>
        <div
          :class="[
            'shrink-0 rounded-full px-2.5 py-1 text-[11px] font-semibold ring-1 ring-inset',
            visibleTeachingStance.classes,
          ]"
        >
          {{ visibleTeachingStance.label }}
        </div>
      </div>

      <div class="grid grid-cols-2 mt-3 gap-2">
        <div
          v-for="fact in visiblePerformanceFacts"
          :key="fact.key"
          :class="[
            'min-w-0 rounded-[14px] border border-sky-100/80 bg-sky-50/55 px-2.5 py-2 dark:border-white/8 dark:bg-white/5',
            fact.key === 'interrupt_policy' ? 'col-span-2' : '',
          ]"
        >
          <div class="text-[10px] text-slate-400 font-semibold tracking-[0.12em] uppercase dark:text-neutral-500">
            {{ fact.label }}
          </div>
          <div
            :data-testid="`lesson-airi-visible-fact-${fact.key}`"
            class="mt-1 truncate text-[11px] text-slate-800 font-semibold dark:text-neutral-100"
          >
            {{ fact.value }}
          </div>
        </div>
      </div>
    </div>

    <div class="sr-only">
      <div>{{ selectedPageUid }}</div>
      <div>{{ currentPageTitle }}</div>
      <div data-testid="lesson-runtime-status-label">
        {{ sidebarRuntimeStatus.label }}
      </div>
      <div data-testid="lesson-runtime-status-meta">
        {{ sidebarRuntimeMetaLabel }}
      </div>
      <div data-testid="lesson-runtime-status-detail">
        {{ sidebarRuntimeStatus.detail }}
      </div>

      <div
        data-testid="lesson-runtime-current-device"
      >
        <div class="text-slate-800 font-medium dark:text-neutral-100">
          当前设备
        </div>
        <div class="mt-1 truncate">
          {{ microphoneInputDeviceLabel || '未连接输入设备' }}
        </div>
      </div>

      <div
        v-for="fact in speechChainFacts"
        :key="fact.key"
      >
        <div class="text-[10px] text-slate-400 font-semibold tracking-[0.12em] uppercase dark:text-neutral-400">
          {{ fact.label }}
        </div>
        <div
          :data-testid="`lesson-runtime-fact-${fact.key}`"
          class="mt-1 truncate text-[11px] text-slate-800 font-medium dark:text-neutral-100"
        >
          {{ fact.value }}
        </div>
      </div>

      <div
        v-if="liveTranscriptText"
        data-testid="lesson-runtime-live-transcript"
      >
        <div class="text-[11px] text-emerald-700/80 font-semibold tracking-[0.18em] uppercase dark:text-emerald-100/80">
          实时转写
        </div>
        <div class="mt-1 text-sm text-emerald-800 leading-6 dark:text-emerald-50">
          {{ liveTranscriptText }}
        </div>
      </div>
    </div>
  </aside>
</template>
