<script setup lang="ts">
import { useLessonStore } from '@proj-airi/stage-ui/stores/lesson'
import {
  lessonRetrievalModeLabels,
  lessonTeachingActionLabels,
} from '@proj-airi/stage-ui/types/lesson'
import { sanitizeLessonVisibleText } from '@proj-airi/stage-ui/utils/lesson-text'
import { Button, Callout, FieldSelect, Input, Progress, SelectTab, useTheme } from '@proj-airi/ui'
import { storeToRefs } from 'pinia'
import { computed, ref, watch } from 'vue'

const props = withDefaults(defineProps<{
  mobile?: boolean
}>(), {
  mobile: false,
})

const lessonStore = useLessonStore()
const {
  availablePages,
  scopedPages,
  selectedPageUid,
  selectedGrade,
  selectedSemester,
  selectedUnit,
  studentId,
  loading,
  error,
  runtimeState,
  activeTurn,
  isConfigured,
  hasStarted,
  currentTeacherPrompt,
  currentPageTitle,
  currentActivityLabel,
  pedagogyProgress,
  selectedScopeLabel,
  catalogCoverageLabel,
  catalogCoverageBadges,
  gradeOptions,
  semesterOptions,
  unitOptions,
} = storeToRefs(lessonStore)
const { isDark, toggleDark } = useTheme()

const pageUidDraft = ref(selectedPageUid.value)

watch(selectedPageUid, (pageUid) => {
  pageUidDraft.value = pageUid
}, { immediate: true })

const gradeTabOptions = computed(() =>
  gradeOptions.value.map(option => ({
    label: option.label,
    value: option.value,
  })),
)

const semesterTabOptions = computed(() =>
  semesterOptions.value.map(option => ({
    label: option.label,
    value: option.value,
  })),
)

const unitSelectOptions = computed(() =>
  unitOptions.value.map(option => ({
    label: option.label,
    value: option.value,
  })),
)

const pageOptions = computed(() =>
  scopedPages.value.map(page => ({
    label: page.label,
    value: page.value,
  })),
)

const selectedGradeTabValue = computed({
  get: () => selectedGrade.value,
  set: (value) => {
    void lessonStore.selectLessonGrade(String(value), {
      restartIfStarted: hasStarted.value,
    })
  },
})

const selectedSemesterTabValue = computed({
  get: () => selectedSemester.value,
  set: (value) => {
    void lessonStore.selectLessonSemester(String(value), {
      restartIfStarted: hasStarted.value,
    })
  },
})

const selectedUnitValue = computed({
  get: () => selectedUnit.value,
  set: (value) => {
    void lessonStore.selectLessonUnit(String(value), {
      restartIfStarted: hasStarted.value,
    })
  },
})

const selectedPageTabValue = computed({
  get: () => selectedPageUid.value,
  set: (value) => {
    void lessonStore.selectLessonPage(String(value), {
      restartIfStarted: hasStarted.value,
    })
  },
})

const selectedPageDescription = computed(() =>
  availablePages.value.find(page => page.value === selectedPageUid.value)?.description || '选择当前 lesson 页面',
)

const selectedScopeFacts = computed(() => {
  if (!scopedPages.value.length) {
    return '当前目录还没有可选页面。'
  }

  const firstPage = scopedPages.value[0]?.label || ''
  const lastPage = scopedPages.value.at(-1)?.label || ''
  return `${selectedScopeLabel.value} · ${scopedPages.value.length} 页 · ${firstPage} - ${lastPage}`
})

const pageSelectorSummary = computed(() => {
  if (!scopedPages.value.length) {
    return '当前 scope 没有页面。'
  }

  return `当前单元 ${scopedPages.value.length} 页，${selectedPageDescription.value}`
})

const pageSelectorDisabled = computed(() => loading.value || pageOptions.value.length === 0)
const pageInputPlaceholder = computed(() => scopedPages.value[0]?.value || 'TB-G5S1U3-P24')

const currentTask = computed(() =>
  sanitizeLessonVisibleText(activeTurn.value?.teacher_response || '')
  || sanitizeLessonVisibleText(currentTeacherPrompt.value || '')
  || '先选择页面并开始本页 lesson。',
)
const currentTaskDetail = computed(() => {
  const detail = selectedPageDescription.value.trim()
  if (!detail || detail === currentTask.value.trim()) {
    return ''
  }

  return detail
})
const studyBoardTitle = computed(() => {
  if (activeTurn.value?.turn_label === 'page_entry') {
    return '教材知识点摘要'
  }

  if (runtimeState.value?.branch_active) {
    return '当前支线提示'
  }

  return '本页学习内容'
})
const studyBoardSummary = computed(() => {
  const detail = currentTaskDetail.value || selectedPageDescription.value
  return detail.replace(/\s+/g, ' ').trim()
})
const studyBoardLines = computed(() => {
  const source = [currentTask.value, currentTaskDetail.value, sanitizeLessonVisibleText(selectedPageDescription.value)]
    .filter(Boolean)
    .join('。')
    .split(/[。!?！？]/)
    .map(line => line.trim())
    .filter(Boolean)

  return source.slice(0, 4)
})

const runtimeTags = computed(() => {
  const tags = [
    selectedScopeLabel.value === '未选择页面' ? '未绑定 scope' : `目录：${selectedScopeLabel.value}`,
    activeTurn.value?.retrieval_mode
      ? `检索：${lessonRetrievalModeLabels[activeTurn.value.retrieval_mode]}`
      : null,
    activeTurn.value?.teaching_action
      ? `动作：${lessonTeachingActionLabels[activeTurn.value.teaching_action]}`
      : null,
    runtimeState.value?.branch_active ? '支线中' : '主线中',
  ]

  if (runtimeState.value?.awaiting_answer) {
    tags.push('等待回答')
  }

  return tags.filter(Boolean) as string[]
})
const compactRuntimeTags = computed(() => runtimeTags.value.slice(0, 2))

function memoryStatusLabel(status: 'success' | 'skipped' | 'degraded') {
  switch (status) {
    case 'success':
      return '成功'
    case 'degraded':
      return '降级'
    case 'skipped':
    default:
      return '跳过'
  }
}

function memoryStatusBadgeClasses(status: 'success' | 'skipped' | 'degraded') {
  switch (status) {
    case 'success':
      return [
        'bg-emerald-100/95',
        'text-emerald-700',
        'dark:bg-emerald-500/20',
        'dark:text-emerald-100',
      ]
    case 'degraded':
      return [
        'bg-rose-100/95',
        'text-rose-700',
        'dark:bg-rose-500/20',
        'dark:text-rose-100',
      ]
    case 'skipped':
    default:
      return [
        'bg-neutral-200/90',
        'text-neutral-600',
        'dark:bg-neutral-800',
        'dark:text-neutral-200',
      ]
  }
}

function memoryDegradationLabel(
  state: 'healthy' | 'idle' | 'memory_disabled' | 'session_degraded' | 'recall_degraded' | 'writeback_degraded' | 'recall_and_writeback_degraded',
) {
  switch (state) {
    case 'healthy':
      return '正常'
    case 'idle':
      return '待机'
    case 'memory_disabled':
      return '已关闭'
    case 'session_degraded':
      return '会话异常'
    case 'recall_degraded':
      return '召回降级'
    case 'writeback_degraded':
      return '写回降级'
    case 'recall_and_writeback_degraded':
      return '召回/写回降级'
    default:
      return state
  }
}

function memoryDegradationBadgeClasses(
  state: 'healthy' | 'idle' | 'memory_disabled' | 'session_degraded' | 'recall_degraded' | 'writeback_degraded' | 'recall_and_writeback_degraded',
) {
  switch (state) {
    case 'healthy':
      return [
        'bg-emerald-100/95',
        'text-emerald-700',
        'dark:bg-emerald-500/20',
        'dark:text-emerald-100',
      ]
    case 'idle':
      return [
        'bg-sky-100/95',
        'text-sky-700',
        'dark:bg-sky-500/20',
        'dark:text-sky-100',
      ]
    case 'memory_disabled':
      return [
        'bg-neutral-200/90',
        'text-neutral-600',
        'dark:bg-neutral-800',
        'dark:text-neutral-200',
      ]
    case 'session_degraded':
    case 'recall_degraded':
    case 'writeback_degraded':
    case 'recall_and_writeback_degraded':
    default:
      return [
        'bg-rose-100/95',
        'text-rose-700',
        'dark:bg-rose-500/20',
        'dark:text-rose-100',
      ]
  }
}

const lessonDebugSignalFacts = computed(() => {
  const debugSignals = activeTurn.value?.debug_signals
  if (!debugSignals) {
    return []
  }

  return [
    {
      key: 'live_prompts',
      label: 'Live prompts',
      status: debugSignals.live_prompts.enabled ? '开启' : '关闭',
      detail: debugSignals.live_prompts.enabled
        ? '本轮 teacher 响应走了 live planner / responder。'
        : '本轮没有走 live prompts。',
    },
    {
      key: 'vector_retrieval',
      label: '向量检索',
      status: debugSignals.vector_retrieval.enabled ? '开启' : '关闭',
      detail: debugSignals.vector_retrieval.hit_modes.length > 0
        ? `命中：${debugSignals.vector_retrieval.hit_modes.join(' / ')}`
        : '未命中 unit / branch 检索。',
    },
    {
      key: 'prompt_memory',
      label: 'Prompt memory',
      status: debugSignals.prompt_memory.enabled ? '开启' : '关闭',
      detail: debugSignals.prompt_memory.injected_buckets.length > 0
        ? `注入：${debugSignals.prompt_memory.injected_buckets.join(' / ')}`
        : '当前没有注入 memory bucket。',
    },
    {
      key: 'semantic_recall',
      label: 'Semantic recall',
      status: debugSignals.semantic_recall.enabled ? '开启' : '关闭',
      detail: debugSignals.semantic_recall.recalled_memories.length > 0
        ? `召回：${debugSignals.semantic_recall.recalled_memories.join('；')}`
        : '当前没有额外召回记忆。',
    },
  ]
})

const lessonMemoryRuntime = computed(() => activeTurn.value?.debug_signals?.memory_runtime || null)

const lessonMemoryIdentityFacts = computed(() => {
  if (!lessonMemoryRuntime.value) {
    return []
  }

  return [
    {
      key: 'student_id',
      label: 'Student ID',
      value: lessonMemoryRuntime.value.student_id,
    },
    {
      key: 'project',
      label: 'Project',
      value: lessonMemoryRuntime.value.project,
    },
    {
      key: 'memory_session_id',
      label: 'Memory session',
      value: lessonMemoryRuntime.value.memory_session_id || '未建立',
    },
  ]
})

const lessonMemoryStatusFacts = computed(() => {
  if (!lessonMemoryRuntime.value) {
    return []
  }

  return [
    {
      key: 'recall',
      label: 'Recall',
      status: lessonMemoryRuntime.value.last_recall_status,
      detail: lessonMemoryRuntime.value.last_recall_summary,
    },
    {
      key: 'writeback',
      label: 'Writeback',
      status: lessonMemoryRuntime.value.last_writeback_status,
      detail: lessonMemoryRuntime.value.last_writeback_summary,
    },
  ]
})

const memoryDegradationClasses = computed(() =>
  lessonMemoryRuntime.value
    ? memoryDegradationBadgeClasses(lessonMemoryRuntime.value.degradation_state)
    : memoryDegradationBadgeClasses('idle'),
)

const lessonRhythmFacts = computed(() => {
  if (!runtimeState.value) {
    return []
  }

  return [
    {
      label: '当前块',
      value: runtimeState.value.current_block_uid || '未绑定',
    },
    {
      label: '提示级别',
      value: String(runtimeState.value.hint_level),
    },
    {
      label: '教学级别',
      value: String(runtimeState.value.pedagogy_level),
    },
    {
      label: '同目标尝试',
      value: String(runtimeState.value.same_goal_attempt_count),
    },
  ]
})

const canStart = computed(() =>
  isConfigured.value
  && Boolean(selectedPageUid.value.trim())
  && Boolean(studentId.value.trim())
  && !loading.value,
)

const canQuickAct = computed(() => hasStarted.value && !loading.value)

const statusBadgeClasses = computed(() => {
  if (!runtimeState.value) {
    return [
      'bg-neutral-100/90',
      'text-neutral-600',
      'dark:bg-neutral-800/90',
      'dark:text-neutral-300',
    ]
  }

  if (runtimeState.value.branch_active) {
    return [
      'bg-violet-100/95',
      'text-violet-700',
      'dark:bg-violet-500/25',
      'dark:text-violet-100',
    ]
  }

  if (runtimeState.value.awaiting_answer) {
    return [
      'bg-amber-100/95',
      'text-amber-700',
      'dark:bg-amber-500/25',
      'dark:text-amber-100',
    ]
  }

  return [
    'bg-emerald-100/95',
    'text-emerald-700',
    'dark:bg-emerald-500/25',
    'dark:text-emerald-100',
  ]
})

async function handleStart() {
  try {
    await lessonStore.startLesson(selectedPageUid.value)
  }
  catch {
  }
}

async function handleHint() {
  try {
    await lessonStore.requestHint()
  }
  catch {
  }
}

async function handleReturn() {
  try {
    await lessonStore.returnToMainline()
  }
  catch {
  }
}

async function handleRepeatPrompt() {
  lessonStore.repeatTeacherPrompt()
}

async function handleCoverageBadgeClick(bucket: { grade: string, semester: string }) {
  await lessonStore.selectLessonGradeSemester(bucket.grade, bucket.semester, {
    restartIfStarted: hasStarted.value,
  })
}

async function applyPageUidDraft() {
  const normalizedPageUid = pageUidDraft.value.trim()
  if (!normalizedPageUid) {
    pageUidDraft.value = selectedPageUid.value
    return
  }

  try {
    await lessonStore.selectLessonPage(normalizedPageUid, {
      restartIfStarted: hasStarted.value,
    })
  }
  catch {
  }

  pageUidDraft.value = selectedPageUid.value
}
</script>

<template>
  <section
    :class="[
      'flex min-h-0 w-full flex-col gap-3',
      props.mobile ? 'h-auto overflow-visible pb-2 pr-0' : 'h-full overflow-y-auto pb-3 pr-1',
    ]"
  >
    <div
      :class="[
        'rounded-[24px] border border-white/55 bg-white/72 p-3.5 shadow-[0_20px_60px_-38px_rgba(15,23,42,0.55)] backdrop-blur-xl',
        'dark:border-neutral-800/70 dark:bg-neutral-950/72',
      ]"
    >
      <div :class="['flex items-start justify-between gap-3']">
        <div :class="['min-w-0']">
          <div :class="['text-[10px] font-semibold uppercase tracking-[0.24em] text-neutral-400 dark:text-neutral-500']">
            PepTutor Lesson
          </div>
          <div :class="['mt-1 line-clamp-2 text-lg font-semibold leading-6 text-neutral-800 dark:text-neutral-50']">
            {{ currentPageTitle }}
          </div>
          <div :class="['mt-1 truncate text-xs text-neutral-500 dark:text-neutral-300']">
            {{ runtimeState?.current_block_uid || selectedPageDescription }}
          </div>
        </div>
        <div class="flex shrink-0 items-center gap-2">
          <button
            class="h-9 flex items-center gap-2 border border-sky-100/90 rounded-full bg-white/78 px-3 text-xs text-slate-600 font-semibold shadow-[0_12px_30px_-24px_rgba(15,23,42,0.75)] transition dark:border-white/10 dark:bg-white/6 hover:bg-sky-50 dark:text-neutral-200 dark:hover:bg-white/10"
            :aria-label="isDark ? '切换到日间模式' : '切换到暗色模式'"
            :title="isDark ? '切换到日间模式' : '切换到暗色模式'"
            type="button"
            @click="toggleDark()"
          >
            <div :class="[isDark ? 'i-solar:moon-bold-duotone' : 'i-solar:sun-2-bold-duotone', 'h-4 w-4']" />
            <span class="hidden xl:inline">{{ isDark ? '暗色' : '日间' }}</span>
          </button>
          <div
            :class="[
              'rounded-full px-3 py-1 text-xs font-semibold',
              ...statusBadgeClasses,
            ]"
          >
            {{ currentActivityLabel }}
          </div>
        </div>
      </div>
    </div>

    <Callout
      v-if="!isConfigured"
      theme="orange"
      label="Lesson API 未配置"
    >
      <p>设置 `VITE_PEPTUTOR_LESSON_API_URL` 后，这个面板才会调用 `POST /lesson/turn`。</p>
      <p>推荐本地值：`http://127.0.0.1:9625`</p>
    </Callout>

    <Callout
      v-else-if="error"
      theme="orange"
      label="Lesson 请求失败"
    >
      <p>{{ error }}</p>
    </Callout>

    <div
      v-if="props.mobile"
      :class="[
        'relative overflow-hidden rounded-[24px] border border-white/55 bg-white/76 p-3.5 backdrop-blur-xl',
        'dark:border-neutral-800/70 dark:bg-neutral-950/72',
      ]"
    >
      <div class="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(56,189,248,0.14),transparent_46%)]" />
      <div class="relative">
        <div class="flex items-center justify-between gap-3">
          <div class="min-w-0">
            <div class="text-[10px] text-neutral-400 font-semibold tracking-[0.22em] uppercase dark:text-neutral-500">
              {{ studyBoardTitle }}
            </div>
            <div class="mt-1 truncate text-[11px] text-neutral-500 dark:text-neutral-400">
              {{ selectedPageUid }}
            </div>
          </div>
          <div class="shrink-0 rounded-full bg-neutral-900 px-2.5 py-1 text-[11px] text-white font-semibold dark:bg-white dark:text-neutral-900">
            {{ activeTurn?.turn_label || 'lesson' }}
          </div>
        </div>

        <div class="line-clamp-4 mt-3 text-[15px] text-neutral-900 font-semibold leading-6 dark:text-neutral-50">
          {{ currentTask }}
        </div>
        <div
          v-if="currentTaskDetail"
          class="line-clamp-2 mt-2 text-xs text-neutral-500 leading-5 dark:text-neutral-300"
        >
          {{ currentTaskDetail }}
        </div>
        <div class="mt-3 flex flex-wrap gap-2">
          <div
            v-for="tag in compactRuntimeTags"
            :key="tag"
            class="rounded-full bg-sky-100/80 px-2.5 py-1 text-[11px] text-sky-700 font-medium dark:bg-white/8 dark:text-neutral-100"
          >
            {{ tag }}
          </div>
        </div>
      </div>
    </div>

    <div
      :class="[
        'grid gap-3',
        props.mobile ? 'grid-cols-1' : 'grid-cols-1',
      ]"
    >
      <div
        :class="[
          'rounded-[24px] border border-white/55 bg-white/76 p-3.5 backdrop-blur-xl',
          'dark:border-neutral-800/70 dark:bg-neutral-950/72',
        ]"
      >
        <div :class="['mb-3 flex items-center justify-between gap-3']">
          <div class="min-w-0">
            <div :class="['text-sm font-semibold text-neutral-700 dark:text-neutral-100']">
              课程控制
            </div>
            <div :class="['mt-0.5 truncate text-[11px] text-neutral-500 dark:text-neutral-400']">
              {{ selectedScopeLabel }} · {{ catalogCoverageLabel }}
            </div>
          </div>
          <Button
            variant="primary"
            size="sm"
            :loading="loading"
            :disabled="!canStart"
            @click="handleStart"
          >
            {{ hasStarted ? '重新开始' : '开始上课' }}
          </Button>
        </div>

        <div class="mb-3 border border-sky-100/90 rounded-[18px] bg-sky-50/68 px-3 py-3 dark:border-sky-300/14 dark:bg-sky-400/8">
          <div class="flex items-center justify-between gap-2">
            <div class="text-[11px] text-sky-700/75 font-semibold tracking-[0.18em] uppercase dark:text-sky-100/75">
              教材目录
            </div>
          </div>
          <div class="grid grid-cols-2 mt-2 gap-2">
            <button
              v-for="bucket in catalogCoverageBadges"
              :key="bucket.key"
              :class="[
                'min-w-0 rounded-full border px-2.5 py-1.5 text-left text-[11px] font-semibold transition disabled:cursor-not-allowed disabled:opacity-55',
                bucket.selected
                  ? 'border-sky-300 bg-white text-sky-700 shadow-[0_12px_28px_-24px_rgba(14,116,144,0.75)] dark:border-sky-300/30 dark:bg-sky-300/14 dark:text-sky-100'
                  : 'border-sky-100/90 bg-white/55 text-slate-600 hover:bg-white dark:border-white/10 dark:bg-white/5 dark:text-neutral-300 dark:hover:bg-white/10',
              ]"
              type="button"
              :disabled="loading"
              :title="bucket.detail"
              @click="void handleCoverageBadgeClick(bucket)"
            >
              <span>{{ bucket.label }}</span>
            </button>
          </div>
        </div>

        <div :class="['grid min-w-0 gap-2.5']">
          <div class="grid grid-cols-2 min-w-0 gap-2.5">
            <div class="min-w-0">
              <div :class="['mb-1.5 text-xs font-medium text-neutral-500 dark:text-neutral-400']">
                年级
              </div>
              <SelectTab
                v-model="selectedGradeTabValue"
                size="sm"
                :options="gradeTabOptions"
                :disabled="loading"
              />
            </div>

            <div class="min-w-0">
              <div :class="['mb-1.5 text-xs font-medium text-neutral-500 dark:text-neutral-400']">
                学期
              </div>
              <SelectTab
                v-model="selectedSemesterTabValue"
                size="sm"
                :options="semesterTabOptions"
                :disabled="loading || semesterTabOptions.length === 0"
              />
            </div>
          </div>

          <FieldSelect
            v-model="selectedUnitValue"
            input-id="lesson-unit-select"
            input-name="lesson-unit-select"
            label="单元"
            :description="scopedPages.length ? selectedScopeFacts : ''"
            :options="unitSelectOptions"
            placeholder="选择单元"
            :disabled="loading || unitSelectOptions.length === 0"
            layout="horizontal"
          />

          <div class="min-w-0">
            <div :class="['mb-1.5 flex items-center justify-between gap-3']">
              <span :class="['text-xs font-medium text-neutral-500 dark:text-neutral-400']">页面</span>
              <span :class="['truncate text-[11px] text-neutral-400 dark:text-neutral-500']">{{ pageSelectorSummary }}</span>
            </div>
            <div class="overflow-x-auto pb-1">
              <div style="min-width: 34rem">
                <SelectTab
                  v-model="selectedPageTabValue"
                  size="sm"
                  :options="pageOptions"
                  :disabled="pageSelectorDisabled"
                />
              </div>
            </div>
          </div>
        </div>

        <details class="mt-3 border border-neutral-200/80 rounded-[16px] bg-white/55 px-3 py-2 dark:border-white/8 dark:bg-white/5">
          <summary class="cursor-pointer text-xs text-neutral-500 font-semibold dark:text-neutral-300">
            高级设置
          </summary>
          <div :class="['mt-3 grid gap-3', props.mobile ? 'grid-cols-1' : 'grid-cols-1']">
            <label :class="['flex flex-col gap-2']">
              <span :class="['text-xs font-medium text-neutral-500 dark:text-neutral-400']">Page UID</span>
              <div :class="['flex gap-2']">
                <Input
                  id="lesson-page-uid-input"
                  v-model="pageUidDraft"
                  name="lesson-page-uid"
                  variant="primary-dimmed"
                  :placeholder="pageInputPlaceholder"
                  @blur="void applyPageUidDraft()"
                  @keydown.enter.prevent="void applyPageUidDraft()"
                />
                <Button
                  variant="secondary"
                  size="sm"
                  :disabled="loading"
                  @click="void applyPageUidDraft()"
                >
                  跳转
                </Button>
              </div>
            </label>

            <label :class="['flex flex-col gap-2']">
              <span :class="['text-xs font-medium text-neutral-500 dark:text-neutral-400']">Student ID</span>
              <Input
                id="lesson-student-id-input"
                v-model="studentId"
                name="lesson-student-id"
                variant="primary-dimmed"
                placeholder="demo-student"
              />
            </label>
          </div>
        </details>
      </div>

      <div class="sr-only">
        <div>{{ currentTask }}</div>
        <div v-if="currentTaskDetail">
          {{ currentTaskDetail }}
        </div>
        <div v-if="runtimeState?.return_anchor">
          回主线锚点：{{ runtimeState.return_anchor }}
        </div>
        <div v-for="tag in runtimeTags" :key="tag">
          {{ tag }}
        </div>
        <div v-for="(line, index) in studyBoardLines" :key="`${index}:${line}`">
          {{ line }}
        </div>
        <div>{{ studyBoardSummary }}</div>
      </div>

      <div
        v-if="lessonDebugSignalFacts.length > 0"
        class="sr-only"
      >
        <div :class="['mb-2 text-sm font-semibold text-neutral-700 dark:text-neutral-100']">
          本轮能力
        </div>
        <div :class="['text-xs text-neutral-500 dark:text-neutral-400']">
          只在后端开启 `PEPTUTOR_DEBUG_SIGNALS=1` 时出现，用来解释这一轮 lesson 实际用了哪些能力。
        </div>

        <div :class="['mt-3 grid gap-2', props.mobile ? 'grid-cols-1' : 'grid-cols-2']">
          <div
            v-for="fact in lessonDebugSignalFacts"
            :key="fact.key"
            :data-testid="`lesson-debug-signal-card-${fact.key}`"
            :class="[
              'rounded-2xl bg-neutral-100/90 px-3 py-3',
              'dark:bg-neutral-900/75',
            ]"
          >
            <div :class="['flex items-center justify-between gap-3']">
              <div :class="['text-xs font-semibold uppercase tracking-[0.18em] text-neutral-400 dark:text-neutral-500']">
                {{ fact.label }}
              </div>
              <div
                :data-testid="`lesson-debug-signal-status-${fact.key}`"
                :class="[
                  'rounded-full px-2 py-1 text-[11px] font-medium',
                  fact.status === '开启'
                    ? 'bg-emerald-100/95 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-100'
                    : 'bg-neutral-200/90 text-neutral-600 dark:bg-neutral-800 dark:text-neutral-200',
                ]"
              >
                {{ fact.status }}
              </div>
            </div>
            <div
              :data-testid="`lesson-debug-signal-detail-${fact.key}`"
              :class="['mt-2 text-sm leading-6 text-neutral-700 dark:text-neutral-100']"
            >
              {{ fact.detail }}
            </div>
          </div>
        </div>
      </div>

      <div
        v-if="lessonMemoryRuntime"
        class="sr-only"
      >
        <div :class="['mb-2 flex items-center justify-between gap-3']">
          <div>
            <div :class="['text-sm font-semibold text-neutral-700 dark:text-neutral-100']">
              Backend Memory
            </div>
            <div :class="['text-xs text-neutral-500 dark:text-neutral-400']">
              当前 lesson 真实使用的 learner-memory 边界、session 和回写状态。
            </div>
          </div>
          <div
            data-testid="lesson-memory-debug-value-degradation_state"
            :class="[
              'rounded-full px-3 py-1 text-xs font-medium',
              ...memoryDegradationClasses,
            ]"
          >
            {{ memoryDegradationLabel(lessonMemoryRuntime.degradation_state) }}
          </div>
        </div>

        <div :class="['grid gap-2', props.mobile ? 'grid-cols-1' : 'grid-cols-2']">
          <div
            v-for="fact in lessonMemoryIdentityFacts"
            :key="fact.key"
            :class="[
              'rounded-2xl bg-neutral-100/90 px-3 py-3',
              'dark:bg-neutral-900/75',
            ]"
          >
            <div :class="['text-[11px] font-semibold uppercase tracking-[0.18em] text-neutral-400 dark:text-neutral-500']">
              {{ fact.label }}
            </div>
            <div
              :data-testid="`lesson-memory-debug-value-${fact.key}`"
              :class="['mt-2 break-all text-sm leading-6 text-neutral-700 dark:text-neutral-100']"
            >
              {{ fact.value }}
            </div>
          </div>
        </div>

        <div :class="['mt-3 grid gap-2', props.mobile ? 'grid-cols-1' : 'grid-cols-2']">
          <div
            v-for="fact in lessonMemoryStatusFacts"
            :key="fact.key"
            :class="[
              'rounded-2xl bg-neutral-100/90 px-3 py-3',
              'dark:bg-neutral-900/75',
            ]"
          >
            <div :class="['flex items-center justify-between gap-3']">
              <div :class="['text-xs font-semibold uppercase tracking-[0.18em] text-neutral-400 dark:text-neutral-500']">
                {{ fact.label }}
              </div>
              <div
                :data-testid="`lesson-memory-debug-status-${fact.key}`"
                :class="[
                  'rounded-full px-2 py-1 text-[11px] font-medium',
                  ...memoryStatusBadgeClasses(fact.status),
                ]"
              >
                {{ memoryStatusLabel(fact.status) }}
              </div>
            </div>
            <div
              :data-testid="`lesson-memory-debug-detail-${fact.key}`"
              :class="['mt-2 text-sm leading-6 text-neutral-700 dark:text-neutral-100']"
            >
              {{ fact.detail }}
            </div>
          </div>
        </div>
      </div>
    </div>

    <div :class="['grid gap-3', props.mobile ? 'grid-cols-1' : 'grid-cols-[1fr_0.92fr]']">
      <div
        :class="[
          'rounded-[24px] border-2 border-solid border-white/50 bg-white/78 p-4 backdrop-blur-xl',
          'dark:border-neutral-800/70 dark:bg-neutral-950/72',
        ]"
      >
        <div :class="['mb-3 text-sm font-semibold text-neutral-700 dark:text-neutral-100']">
          动作按钮
        </div>
        <div :class="['grid grid-cols-2 gap-2']">
          <Button
            variant="secondary"
            size="sm"
            icon="i-solar:restart-bold-duotone"
            :disabled="!canStart"
            @click="handleStart"
          >
            重新开始
          </Button>
          <Button
            variant="secondary"
            size="sm"
            icon="i-solar:chat-round-call-bold-duotone"
            :disabled="!canQuickAct"
            @click="handleHint"
          >
            给提示
          </Button>
          <Button
            variant="secondary"
            size="sm"
            icon="i-solar:round-arrow-left-bold-duotone"
            :disabled="!canQuickAct"
            @click="handleReturn"
          >
            回主线
          </Button>
          <Button
            variant="secondary"
            size="sm"
            icon="i-solar:playback-speed-bold-duotone"
            :disabled="!hasStarted"
            @click="handleRepeatPrompt"
          >
            再听一遍
          </Button>
        </div>
      </div>

      <div
        :class="[
          'rounded-[24px] border-2 border-solid border-white/50 bg-white/78 p-4 backdrop-blur-xl',
          'dark:border-neutral-800/70 dark:bg-neutral-950/72',
        ]"
      >
        <div :class="['mb-2 text-sm font-semibold text-neutral-700 dark:text-neutral-100']">
          页面节奏
        </div>
        <div :class="['text-xs text-neutral-500 dark:text-neutral-400']">
          当前显示的不是整页真实完成度，而是 lesson 节奏和纠错深度。
        </div>

        <div :class="['mt-3']">
          <Progress :progress="pedagogyProgress" />
        </div>

        <div :class="['mt-3 grid grid-cols-2 gap-2']">
          <div
            v-for="fact in lessonRhythmFacts"
            :key="fact.label"
            :class="[
              'rounded-2xl bg-neutral-100/90 px-3 py-2',
              'dark:bg-neutral-900/75',
            ]"
          >
            <div :class="['text-[11px] uppercase tracking-[0.18em] text-neutral-400 dark:text-neutral-500']">
              {{ fact.label }}
            </div>
            <div :class="['mt-1 line-clamp-2 text-sm text-neutral-700 dark:text-neutral-100']">
              {{ fact.value }}
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>
