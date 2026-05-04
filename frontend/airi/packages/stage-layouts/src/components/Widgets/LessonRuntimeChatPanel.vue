<script setup lang="ts">
import type { ChatHistoryItem } from '@proj-airi/stage-ui/types/chat'

import { ChatHistory } from '@proj-airi/stage-ui/components'
import { useChatOrchestratorStore } from '@proj-airi/stage-ui/stores/chat'
import { useChatSessionStore } from '@proj-airi/stage-ui/stores/chat/session-store'
import { useChatStreamStore } from '@proj-airi/stage-ui/stores/chat/stream-store'
import { useLessonStore } from '@proj-airi/stage-ui/stores/lesson'
import { useLessonAiriRuntimeStore } from '@proj-airi/stage-ui/stores/lesson-airi-runtime'
import { useLessonChatHistoryStore } from '@proj-airi/stage-ui/stores/lesson-chat-history'
import { createPepTutorLessonChatProvider, LESSON_CHAT_MODEL } from '@proj-airi/stage-ui/stores/lesson-chat-provider'
import { useHearingStore } from '@proj-airi/stage-ui/stores/modules/hearing'
import { useSpeechStore } from '@proj-airi/stage-ui/stores/modules/speech'
import { useDeferredMount } from '@proj-airi/ui'
import { storeToRefs } from 'pinia'
import { computed, ref } from 'vue'

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
const lessonChatHistoryStore = useLessonChatHistoryStore()
const { isConfigured, hasStarted } = storeToRefs(lessonStore)
const { activeHistoryReadOnly, activeLessonTabReadOnly } = storeToRefs(lessonChatHistoryStore)
const { microphoneStatus, microphoneStatusLabel, autoSendEnabled } = storeToRefs(lessonAiriRuntime)
const { activeSpeechProvider, activeSpeechModel, activeSpeechVoiceId } = storeToRefs(useSpeechStore())
const { activeTranscriptionProvider, activeTranscriptionModel } = storeToRefs(useHearingStore())
const { isReady } = useDeferredMount()
const { sending } = storeToRefs(useChatOrchestratorStore())
const chatSessionStore = useChatSessionStore()
const { messages } = storeToRefs(chatSessionStore)
const { streamingMessage } = storeToRefs(useChatStreamStore())

const isLoading = ref(true)
const historyMessages = computed(() => messages.value as unknown as ChatHistoryItem[])
const chatDisabled = computed(() => !isConfigured.value || !hasStarted.value || activeLessonTabReadOnly.value)
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
const placeholder = computed(() =>
  activeLessonTabReadOnly.value
    ? '旧 lesson 标签页只读，当前写入已交给最新标签页'
    : activeHistoryReadOnly.value && !hasStarted.value
      ? '历史只读，不能继续发送'
      : hasStarted.value
        ? '说话或输入回答'
        : '先点击开始上课',
)
async function ensureWritableLessonChatSession() {
  await lessonChatHistoryStore.ensureCurrentLessonHistorySession()
  if (lessonChatHistoryStore.activeHistoryReadOnly) {
    throw new Error('历史只读，不能继续发送')
  }
}
const lessonRuntimeBadge = computed(() => {
  if (activeLessonTabReadOnly.value) {
    return {
      label: '只读标签页',
      classes: 'bg-amber-100/95 text-amber-700 dark:bg-amber-500/20 dark:text-amber-100',
    }
  }

  if (activeHistoryReadOnly.value) {
    return {
      label: '只读历史',
      classes: 'bg-amber-100/95 text-amber-700 dark:bg-amber-500/20 dark:text-amber-100',
    }
  }

  if (hasStarted.value) {
    return {
      label: '已接入',
      classes: 'bg-emerald-100/95 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-100',
    }
  }

  return {
    label: '未开始',
    classes: 'bg-neutral-100/90 text-neutral-500 dark:bg-neutral-800/80 dark:text-neutral-300',
  }
})
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
        :before-send="ensureWritableLessonChatSession"
        push-to-talk-hotkey
        compact-mode
      />
    </template>

    <template v-else>
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div class="min-w-0">
          <div class="text-sm text-slate-900 font-semibold dark:text-neutral-100">
            {{ panelTitle }}
          </div>
          <div class="text-xs text-slate-500 dark:text-neutral-400">
            {{ panelSubtitle }}
          </div>
        </div>

        <div class="flex items-center gap-2">
          <button
            v-if="props.dockMode"
            class="h-9 w-9 flex items-center justify-center border border-sky-100/90 rounded-full bg-white/70 text-slate-600 transition dark:border-white/12 dark:bg-white/6 hover:bg-sky-50 dark:text-neutral-100 dark:hover:bg-white/12"
            :aria-label="historyExpanded ? '收起对话记录' : '展开对话记录'"
            :title="historyExpanded ? '收起对话记录' : '展开对话记录'"
            @click="historyExpanded = !historyExpanded"
          >
            <div :class="historyExpanded ? 'i-solar:alt-arrow-down-linear' : 'i-solar:alt-arrow-up-linear'" class="h-4 w-4" />
          </button>

          <div class="rounded-full bg-sky-100/75 px-3 py-1 text-xs text-slate-600 font-medium dark:bg-white/8 dark:text-neutral-100">
            {{ conversationTurnCount }} 条对话
          </div>
          <div
            :class="[
              'rounded-full px-3 py-1 text-xs font-medium',
              lessonRuntimeBadge.classes,
            ]"
          >
            {{ lessonRuntimeBadge.label }}
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
        <div class="rounded-full bg-sky-100/75 px-3 py-1 text-xs text-slate-600 font-medium dark:bg-white/8 dark:text-neutral-200">
          {{ speechProviderLabel }}
        </div>
        <div class="rounded-full bg-sky-100/75 px-3 py-1 text-xs text-slate-600 font-medium dark:bg-white/8 dark:text-neutral-200">
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
              <div class="text-sm text-slate-900 font-semibold dark:text-white">
                聊天记录
              </div>
              <div class="text-xs text-slate-500 dark:text-neutral-400">
                AIRI runtime 与 lesson turn 的合并对话视图
              </div>
            </div>
            <div class="rounded-full bg-sky-100/75 px-3 py-1 text-[11px] text-slate-600 font-medium dark:bg-white/8 dark:text-neutral-200">
              {{ historyExpanded ? '展开中' : '已收起' }}
            </div>
          </div>

          <div class="relative min-h-0 flex flex-1 flex-col overflow-hidden rounded-lg px-2 py-3 md:px-0">
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
            class="rounded-full bg-sky-100/75 px-3 py-1 text-slate-700 font-medium transition dark:bg-white/8 hover:bg-white dark:text-neutral-100 dark:hover:bg-white/12"
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
          :before-send="ensureWritableLessonChatSession"
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
