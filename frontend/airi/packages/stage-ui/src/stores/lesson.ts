import type {
  LessonCatalogOutline,
  LessonCatalogScopeRecord,
  LessonPageOption,
  LessonRuntimeState,
  LessonScopeOption,
  LessonTranscriptEntry,
  LessonTurnResult,
  LessonTurnStreamRequest,
} from '../types/lesson'

import { nanoid } from 'nanoid'
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { useLlmmarkerParser } from '../composables/llm-marker-parser'
import {
  buildLessonPageOptionsFromCatalog,
  buildLessonPageOptionsFromScope,
  buildLessonScopeLabel,
  findLessonCatalogScopeByPageUid,
  lessonActivityTypeLabels,
  lessonPilotCatalogOutline,
  lessonPilotPageOptions,
} from '../types/lesson'
import { resolveLessonPageUid } from '../utils/lesson-route'
import { stripLessonMarkdown } from '../utils/lesson-text'
import { resolvePepTutorRuntimeEnv } from '../utils/peptutor-runtime-config'
import { fetchPepTutorBackend } from './peptutor-backend-auth'
import { useSpeechRuntimeStore } from './speech-runtime'

let lessonApiBaseUrlOverride: string | undefined
const fallbackLessonCatalog = lessonPilotCatalogOutline
const fallbackLessonPageOptions = lessonPilotPageOptions
const defaultLessonPageUid = fallbackLessonPageOptions[0]?.value || ''
const lessonLastPageStorageKey = 'peptutor/lesson/last-page-uid'
const lessonSpeechOwnerId = 'peptutor-lesson'

export interface LessonRuntimeSnapshot {
  version: 1
  selectedPageUid: string
  studentId: string
  runtimeState: LessonRuntimeState | null
  activeTurn: LessonTurnResult | null
  transcript: LessonTranscriptEntry[]
  updatedAt: number
}

function normalizeLessonApiBaseUrl(value?: string | null): string {
  return value?.trim().replace(/\/+$/, '') || ''
}

function resolveLessonApiBaseUrl(): string {
  const configuredBaseUrl = lessonApiBaseUrlOverride ?? normalizeLessonApiBaseUrl(
    resolvePepTutorRuntimeEnv().VITE_PEPTUTOR_LESSON_API_URL,
  )

  return configuredBaseUrl || '/peptutor-api'
}

function readPersistedLessonPageUid() {
  if (typeof localStorage === 'undefined') {
    return ''
  }

  try {
    return localStorage.getItem(lessonLastPageStorageKey)?.trim() || ''
  }
  catch {
    return ''
  }
}

function persistLessonPageUid(value: string) {
  if (typeof localStorage === 'undefined') {
    return
  }

  const normalizedPageUid = value.trim()
  if (!normalizedPageUid) {
    return
  }

  try {
    localStorage.setItem(lessonLastPageStorageKey, normalizedPageUid)
  }
  catch {
  }
}

async function parseLessonError(response: Response): Promise<string> {
  try {
    const payload = await response.json() as { detail?: string }
    if (typeof payload.detail === 'string' && payload.detail.trim()) {
      return payload.detail.trim()
    }
  }
  catch {
  }

  return `Lesson request failed (${response.status})`
}

function buildTranscriptEntry(
  entry: Omit<LessonTranscriptEntry, 'id' | 'created_at'>,
): LessonTranscriptEntry {
  return {
    id: nanoid(),
    created_at: Date.now(),
    ...entry,
  }
}

export function setLessonApiBaseUrlForTest(value?: string) {
  lessonApiBaseUrlOverride = value === undefined ? undefined : normalizeLessonApiBaseUrl(value)
}

export const useLessonStore = defineStore('lesson', () => {
  const speechRuntimeStore = useSpeechRuntimeStore()
  const preferredPageUid = ref(readPersistedLessonPageUid() || defaultLessonPageUid)
  const catalogOutline = ref<LessonCatalogOutline>(fallbackLessonCatalog)
  const selectedPageUid = ref(preferredPageUid.value || defaultLessonPageUid)
  const selectedGrade = ref('')
  const selectedSemester = ref('')
  const selectedUnit = ref('')
  const studentId = ref('demo-student')
  const draftLearnerInput = ref('')
  const loading = ref(false)
  const error = ref<string | null>(null)
  const runtimeState = ref<LessonRuntimeState | null>(null)
  const activeTurn = ref<LessonTurnResult | null>(null)
  const transcript = ref<LessonTranscriptEntry[]>([])
  const catalogLoaded = ref(false)
  const activeTurnClientId = ref<string | null>(null)
  let activeTurnAbortController: AbortController | null = null

  const apiBaseUrl = computed(() => resolveLessonApiBaseUrl())
  const apiCatalogUrl = computed(() => apiBaseUrl.value ? `${apiBaseUrl.value}/lesson/catalog` : '')
  const apiTurnUrl = computed(() => apiBaseUrl.value ? `${apiBaseUrl.value}/lesson/turn` : '')
  const apiTurnStreamUrl = computed(() => apiBaseUrl.value ? `${apiBaseUrl.value}/lesson/turn/stream` : '')
  const isConfigured = computed(() => Boolean(apiTurnUrl.value))
  const scopeRecords = computed(() => catalogOutline.value.scopes)
  const catalogScopeCount = computed(() => scopeRecords.value.length)
  const catalogPageCount = computed(() =>
    scopeRecords.value.reduce((total, scope) => total + scope.pages.length, 0),
  )
  const catalogCoverageLabel = computed(() =>
    `${catalogScopeCount.value} 个 scope · ${catalogPageCount.value} 页`,
  )
  const catalogCoverageBadges = computed(() => {
    const buckets = new Map<string, {
      grade: string
      semester: string
      scopeCount: number
      pageCount: number
    }>()

    for (const scope of scopeRecords.value) {
      const key = `${scope.grade}:${scope.semester}`
      const bucket = buckets.get(key) || {
        grade: scope.grade,
        semester: scope.semester,
        scopeCount: 0,
        pageCount: 0,
      }

      bucket.scopeCount += 1
      bucket.pageCount += scope.pages.length
      buckets.set(key, bucket)
    }

    return [...buckets.values()].map(bucket => ({
      key: `${bucket.grade}:${bucket.semester}`,
      label: `${bucket.grade} ${bucket.semester}`,
      detail: `${bucket.scopeCount} 单元 / ${bucket.pageCount} 页`,
      grade: bucket.grade,
      semester: bucket.semester,
      selected: bucket.grade === selectedGrade.value && bucket.semester === selectedSemester.value,
    }))
  })
  const availablePages = computed<LessonPageOption[]>(() => buildLessonPageOptionsFromCatalog(catalogOutline.value))
  const selectedScope = computed<LessonCatalogScopeRecord | null>(() =>
    scopeRecords.value.find(scope =>
      scope.grade === selectedGrade.value
      && scope.semester === selectedSemester.value
      && scope.unit === selectedUnit.value,
    ) || null,
  )
  const scopedPages = computed<LessonPageOption[]>(() =>
    selectedScope.value ? buildLessonPageOptionsFromScope(selectedScope.value) : [],
  )
  const gradeOptions = computed<LessonScopeOption[]>(() => {
    const seen = new Set<string>()
    const options: LessonScopeOption[] = []

    for (const scope of scopeRecords.value) {
      if (seen.has(scope.grade)) {
        continue
      }

      seen.add(scope.grade)
      options.push({
        label: scope.grade,
        value: scope.grade,
      })
    }

    return options
  })
  const semesterOptions = computed<LessonScopeOption[]>(() => {
    const seen = new Set<string>()
    const options: LessonScopeOption[] = []

    for (const scope of scopeRecords.value) {
      if (scope.grade !== selectedGrade.value || seen.has(scope.semester)) {
        continue
      }

      seen.add(scope.semester)
      options.push({
        label: scope.semester,
        value: scope.semester,
      })
    }

    return options
  })
  const unitOptions = computed<LessonScopeOption[]>(() =>
    scopeRecords.value
      .filter(scope => scope.grade === selectedGrade.value && scope.semester === selectedSemester.value)
      .map(scope => ({
        label: scope.unit,
        value: scope.unit,
      })),
  )
  const selectedScopeLabel = computed(() =>
    selectedScope.value ? buildLessonScopeLabel(selectedScope.value) : '未选择页面',
  )
  const selectedPageOption = computed(() =>
    availablePages.value.find(page => page.value === selectedPageUid.value) || null,
  )
  const defaultPageUid = computed(() => scopedPages.value[0]?.value || availablePages.value[0]?.value || defaultLessonPageUid)
  const hasStarted = computed(() => Boolean(runtimeState.value))
  const currentTeacherPrompt = computed(() =>
    runtimeState.value?.last_teacher_question?.trim()
    || activeTurn.value?.teacher_response?.trim()
    || '',
  )
  const currentPageTitle = computed(() => {
    if (!runtimeState.value) {
      return selectedPageOption.value?.label || selectedPageUid.value || '未开始'
    }

    return `${runtimeState.value.current_grade} ${runtimeState.value.current_semester} ${runtimeState.value.current_unit} · P${runtimeState.value.current_page}`
  })
  const currentActivityLabel = computed(() =>
    runtimeState.value
      ? lessonActivityTypeLabels[runtimeState.value.current_activity_type]
      : '未开始',
  )
  const pedagogyProgress = computed(() => {
    const level = runtimeState.value?.pedagogy_level ?? 0
    return Math.min(100, Math.max(18, ((level + 1) / 4) * 100))
  })
  const latestTeacherLine = computed(() => {
    return [...transcript.value]
      .reverse()
      .find(entry => entry.speaker === 'teacher')
      ?.text || activeTurn.value?.teacher_response || ''
  })

  async function replayTeacherPrompt(text: string, reason: string = 'lesson-teacher-prompt') {
    const normalizedText = stripLessonMarkdown(text)
    if (!normalizedText) {
      return
    }

    speechRuntimeStore.stopByOwner(lessonSpeechOwnerId, reason)
    const intent = speechRuntimeStore.openIntent({
      ownerId: lessonSpeechOwnerId,
      priority: 'high',
      behavior: 'interrupt',
    })

    const parser = useLlmmarkerParser({
      onLiteral: async (literal) => {
        if (literal) {
          intent.writeLiteral(literal)
        }
      },
      onSpecial: async (special) => {
        if (special) {
          intent.writeSpecial(special)
        }
      },
    })

    await parser.consume(normalizedText)
    await parser.end()
    intent.writeFlush()
    intent.end()
  }

  function queueTeacherPromptReplay(text: string, reason: string) {
    void replayTeacherPrompt(text, reason).catch((caughtError) => {
      console.warn('Failed to replay lesson teacher prompt', caughtError)
    })
  }

  function setSelectedScope(scope: LessonCatalogScopeRecord) {
    selectedGrade.value = scope.grade
    selectedSemester.value = scope.semester
    selectedUnit.value = scope.unit
  }

  function resolveKnownLessonPageUid(
    pageUid: string,
    fallbackPageUid: string = preferredPageUid.value || selectedPageUid.value || defaultPageUid.value,
  ) {
    return resolveLessonPageUid(
      pageUid,
      availablePages.value.map(page => page.value),
      fallbackPageUid,
    )
  }

  function commitSelectedPageUid(
    pageUid: string,
    options: { persist?: boolean, prefer?: boolean } = {},
  ) {
    const normalizedPageUid = pageUid.trim()
    selectedPageUid.value = normalizedPageUid

    if (options.prefer !== false && normalizedPageUid) {
      preferredPageUid.value = normalizedPageUid
    }

    if (options.persist !== false && normalizedPageUid) {
      persistLessonPageUid(normalizedPageUid)
    }
  }

  function ensureSelectedScope(preferredPageUid?: string): LessonCatalogScopeRecord | null {
    const preferredScope = preferredPageUid
      ? findLessonCatalogScopeByPageUid(catalogOutline.value, preferredPageUid)
      : null

    if (preferredScope) {
      setSelectedScope(preferredScope)
      return preferredScope
    }

    if (selectedScope.value) {
      return selectedScope.value
    }

    const firstScope = scopeRecords.value[0] || null
    if (firstScope) {
      setSelectedScope(firstScope)
    }

    return firstScope
  }

  function syncSelectedPageToScope(scope: LessonCatalogScopeRecord, preferredPageUid?: string) {
    const normalizedPreferredPageUid = preferredPageUid?.trim() || ''
    const nextPageUid
      = scope.pages.find(page => page.page_uid === normalizedPreferredPageUid)?.page_uid
        || scope.pages.find(page => page.page_uid === selectedPageUid.value)?.page_uid
        || scope.pages[0]?.page_uid
        || ''

    if (nextPageUid) {
      commitSelectedPageUid(nextPageUid, {
        persist: false,
        prefer: false,
      })
    }
  }

  function ensureCatalogSelection(preferredPageUid?: string) {
    const nextScope = ensureSelectedScope(preferredPageUid)
    if (!nextScope) {
      commitSelectedPageUid(defaultLessonPageUid, {
        persist: false,
        prefer: false,
      })
      return
    }

    syncSelectedPageToScope(nextScope, preferredPageUid)
  }

  function resolveScopeForGrade(grade: string): LessonCatalogScopeRecord | null {
    const normalizedGrade = grade.trim()
    return scopeRecords.value.find(scope =>
      scope.grade === normalizedGrade
      && scope.semester === selectedSemester.value
      && scope.unit === selectedUnit.value,
    )
    || scopeRecords.value.find(scope =>
      scope.grade === normalizedGrade
      && scope.semester === selectedSemester.value,
    )
    || scopeRecords.value.find(scope => scope.grade === normalizedGrade)
    || null
  }

  function resolveScopeForSemester(semester: string): LessonCatalogScopeRecord | null {
    const normalizedSemester = semester.trim()
    return scopeRecords.value.find(scope =>
      scope.grade === selectedGrade.value
      && scope.semester === normalizedSemester
      && scope.unit === selectedUnit.value,
    )
    || scopeRecords.value.find(scope =>
      scope.grade === selectedGrade.value
      && scope.semester === normalizedSemester,
    )
    || null
  }

  function resolveScopeForGradeSemester(grade: string, semester: string): LessonCatalogScopeRecord | null {
    const normalizedGrade = grade.trim()
    const normalizedSemester = semester.trim()
    return scopeRecords.value.find(scope =>
      scope.grade === normalizedGrade
      && scope.semester === normalizedSemester
      && scope.unit === selectedUnit.value,
    )
    || scopeRecords.value.find(scope =>
      scope.grade === normalizedGrade
      && scope.semester === normalizedSemester,
    )
    || null
  }

  function resolveScopeForUnit(unit: string): LessonCatalogScopeRecord | null {
    const normalizedUnit = unit.trim()
    return scopeRecords.value.find(scope =>
      scope.grade === selectedGrade.value
      && scope.semester === selectedSemester.value
      && scope.unit === normalizedUnit,
    ) || null
  }

  function setSelectedPageUid(value: string) {
    const normalizedPageUid = value.trim()
    commitSelectedPageUid(normalizedPageUid, {
      persist: false,
      prefer: false,
    })

    const matchingScope = findLessonCatalogScopeByPageUid(catalogOutline.value, normalizedPageUid)
    if (matchingScope) {
      setSelectedScope(matchingScope)
      syncSelectedPageToScope(matchingScope, normalizedPageUid)
      commitSelectedPageUid(normalizedPageUid)
    }
  }

  async function loadCatalog(options: { force?: boolean } = {}) {
    if (!apiCatalogUrl.value) {
      catalogOutline.value = fallbackLessonCatalog
      ensureCatalogSelection(preferredPageUid.value || selectedPageUid.value)
      catalogLoaded.value = false
      return availablePages.value
    }

    if (catalogLoaded.value && !options.force) {
      return availablePages.value
    }

    try {
      const response = await fetchPepTutorBackend(apiCatalogUrl.value, {
        method: 'GET',
      })

      if (!response.ok) {
        throw new Error(await parseLessonError(response))
      }

      const payload = await response.json() as LessonCatalogOutline
      const nextPages = buildLessonPageOptionsFromCatalog(payload)

      catalogOutline.value = nextPages.length > 0 ? payload : fallbackLessonCatalog
      ensureCatalogSelection(preferredPageUid.value || selectedPageUid.value)

      catalogLoaded.value = true
      return availablePages.value
    }
    catch {
      catalogOutline.value = fallbackLessonCatalog
      ensureCatalogSelection(preferredPageUid.value || selectedPageUid.value)
      catalogLoaded.value = false
      return availablePages.value
    }
  }

  async function applyScopeSelection(scope: LessonCatalogScopeRecord, options: { restartIfStarted?: boolean } = {}) {
    setSelectedScope(scope)
    const nextPageUid
      = scope.pages.find(page => page.page_uid === selectedPageUid.value)?.page_uid
        || scope.pages[0]?.page_uid
        || ''

    if (!nextPageUid) {
      commitSelectedPageUid('', {
        persist: false,
        prefer: false,
      })
      return
    }

    await selectLessonPage(nextPageUid, options)
  }

  async function selectLessonGrade(grade: string, options: { restartIfStarted?: boolean } = {}) {
    const nextScope = resolveScopeForGrade(grade)
    if (!nextScope) {
      return
    }

    await applyScopeSelection(nextScope, options)
  }

  async function selectLessonSemester(semester: string, options: { restartIfStarted?: boolean } = {}) {
    const nextScope = resolveScopeForSemester(semester)
    if (!nextScope) {
      return
    }

    await applyScopeSelection(nextScope, options)
  }

  async function selectLessonGradeSemester(grade: string, semester: string, options: { restartIfStarted?: boolean } = {}) {
    const nextScope = resolveScopeForGradeSemester(grade, semester)
    if (!nextScope) {
      return
    }

    await applyScopeSelection(nextScope, options)
  }

  async function selectLessonUnit(unit: string, options: { restartIfStarted?: boolean } = {}) {
    const nextScope = resolveScopeForUnit(unit)
    if (!nextScope) {
      return
    }

    await applyScopeSelection(nextScope, options)
  }

  async function selectLessonPage(pageUid: string, options: { restartIfStarted?: boolean } = {}) {
    const normalizedPageUid = resolveKnownLessonPageUid(pageUid)
    const activePageUid = runtimeState.value?.current_page_uid?.trim() || ''
    const matchingScope = findLessonCatalogScopeByPageUid(catalogOutline.value, normalizedPageUid)

    commitSelectedPageUid(normalizedPageUid)
    if (matchingScope) {
      setSelectedScope(matchingScope)
      syncSelectedPageToScope(matchingScope, normalizedPageUid)
    }

    if (!options.restartIfStarted || !runtimeState.value || !normalizedPageUid || normalizedPageUid === activePageUid) {
      return
    }

    if (loading.value) {
      return
    }

    await startLesson(normalizedPageUid)
  }

  function setStudentId(value: string) {
    studentId.value = value
  }

  function setDraftLearnerInput(value: string) {
    draftLearnerInput.value = value
  }

  function appendDraftLearnerInput(value: string) {
    const normalizedValue = value.trim()
    if (!normalizedValue) {
      return
    }

    const currentValue = draftLearnerInput.value.trim()
    draftLearnerInput.value = currentValue ? `${currentValue} ${normalizedValue}` : normalizedValue
  }

  function resetLessonState(options: { keepSelectedPage?: boolean } = {}) {
    abortActiveTurn('lesson-reset')
    error.value = null
    loading.value = false
    runtimeState.value = null
    activeTurn.value = null
    transcript.value = []
    draftLearnerInput.value = ''

    if (!options.keepSelectedPage) {
      commitSelectedPageUid(defaultPageUid.value, {
        persist: false,
        prefer: false,
      })
    }
  }

  function snapshotValue<T>(value: T): T {
    return JSON.parse(JSON.stringify(value)) as T
  }

  function exportRuntimeSnapshot(): LessonRuntimeSnapshot {
    return {
      version: 1,
      selectedPageUid: selectedPageUid.value,
      studentId: studentId.value,
      runtimeState: runtimeState.value ? snapshotValue(runtimeState.value) : null,
      activeTurn: activeTurn.value ? snapshotValue(activeTurn.value) : null,
      transcript: snapshotValue(transcript.value),
      updatedAt: Date.now(),
    }
  }

  function restoreRuntimeSnapshot(snapshot: LessonRuntimeSnapshot) {
    abortActiveTurn('lesson-session-restore')
    error.value = null
    loading.value = false

    const pageUid = snapshot.selectedPageUid
      || snapshot.runtimeState?.current_page_uid
      || selectedPageUid.value
      || defaultPageUid.value

    if (pageUid) {
      setSelectedPageUid(pageUid)
    }

    studentId.value = snapshot.studentId || studentId.value || 'demo-student'
    runtimeState.value = snapshot.runtimeState ? snapshotValue(snapshot.runtimeState) : null
    activeTurn.value = snapshot.activeTurn ? snapshotValue(snapshot.activeTurn) : null
    transcript.value = snapshotValue(snapshot.transcript || [])
    draftLearnerInput.value = ''
  }

  function applyTurnResult(result: LessonTurnResult, options: { replaceTranscript?: boolean } = {}) {
    runtimeState.value = result.state
    activeTurn.value = result

    const teacherEntry = buildTranscriptEntry({
      speaker: 'teacher',
      text: result.teacher_response,
      turn_label: result.turn_label,
      teaching_action: result.teaching_action,
      retrieval_mode: result.retrieval_mode,
      evaluation: result.evaluation,
    })

    if (options.replaceTranscript) {
      transcript.value = [teacherEntry]
      return
    }

    transcript.value.push(teacherEntry)
  }

  async function sendLessonRequest(payload: Record<string, unknown>) {
    if (!apiTurnUrl.value) {
      throw new Error('VITE_PEPTUTOR_LESSON_API_URL is not configured')
    }

    const response = await fetchPepTutorBackend(apiTurnUrl.value, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    })

    if (!response.ok) {
      throw new Error(await parseLessonError(response))
    }

    return await response.json() as LessonTurnResult
  }

  function isActiveLessonTurn(turnClientId: string | null | undefined) {
    return Boolean(turnClientId && activeTurnClientId.value === turnClientId)
  }

  function beginStreamedTurn(learnerInput: string): LessonTurnStreamRequest {
    if (!runtimeState.value) {
      throw new Error('Lesson has not started yet')
    }

    const text = learnerInput.trim()
    if (!text) {
      throw new Error('Learner input cannot be empty')
    }

    if (!apiTurnStreamUrl.value) {
      throw new Error('VITE_PEPTUTOR_LESSON_API_URL is not configured')
    }

    if (activeTurnAbortController) {
      activeTurnAbortController.abort('lesson-new-turn')
      speechRuntimeStore.stopAll('lesson-new-turn')
    }

    const turnClientId = `lesson-turn-${nanoid()}`
    const abortController = new AbortController()
    activeTurnAbortController = abortController
    activeTurnClientId.value = turnClientId
    loading.value = true
    error.value = null
    draftLearnerInput.value = ''

    transcript.value.push(buildTranscriptEntry({
      speaker: 'learner',
      text,
    }))

    return {
      url: apiTurnStreamUrl.value,
      turnClientId,
      learnerInput: text,
      signal: abortController.signal,
      payload: {
        page_uid: selectedPageUid.value,
        student_id: studentId.value.trim() || 'demo-student',
        learner_input: text,
        state: runtimeState.value,
        turn_client_id: turnClientId,
      },
    }
  }

  function clearActiveStreamTurn(turnClientId: string | null | undefined) {
    if (!isActiveLessonTurn(turnClientId)) {
      return false
    }

    activeTurnAbortController = null
    activeTurnClientId.value = null
    loading.value = false
    return true
  }

  function applyStreamedTurnResult(turnClientId: string, result: LessonTurnResult) {
    if (!isActiveLessonTurn(turnClientId)) {
      return false
    }

    applyTurnResult(result)
    clearActiveStreamTurn(turnClientId)
    return true
  }

  function failStreamedTurn(turnClientId: string, message: string) {
    if (!isActiveLessonTurn(turnClientId)) {
      return false
    }

    error.value = message
    transcript.value.push(buildTranscriptEntry({
      speaker: 'system',
      text: message,
    }))
    clearActiveStreamTurn(turnClientId)
    return true
  }

  function completeStreamedTurn(turnClientId: string) {
    return clearActiveStreamTurn(turnClientId)
  }

  function abortActiveTurn(reason: string = 'lesson-turn-abort') {
    if (!activeTurnAbortController) {
      activeTurnClientId.value = null
      loading.value = false
      return false
    }

    activeTurnAbortController.abort(reason)
    activeTurnAbortController = null
    activeTurnClientId.value = null
    loading.value = false
    speechRuntimeStore.stopAll(reason)
    return true
  }

  async function startLesson(pageUid: string = selectedPageUid.value, options: { replayTeacher?: boolean } = {}) {
    const normalizedPageUid = resolveKnownLessonPageUid(pageUid)
    if (!normalizedPageUid) {
      throw new Error('page_uid is required to start a lesson')
    }

    loading.value = true
    error.value = null
    commitSelectedPageUid(normalizedPageUid)
    draftLearnerInput.value = ''

    try {
      const result = await sendLessonRequest({
        page_uid: normalizedPageUid,
        student_id: studentId.value.trim() || 'demo-student',
      })
      if (selectedPageUid.value !== normalizedPageUid) {
        return result
      }
      applyTurnResult(result, { replaceTranscript: true })
      if (options.replayTeacher !== false) {
        queueTeacherPromptReplay(result.teacher_response, 'lesson-start')
      }
      return result
    }
    catch (caughtError) {
      const message = caughtError instanceof Error ? caughtError.message : 'Failed to start lesson'
      error.value = message
      throw caughtError
    }
    finally {
      loading.value = false
    }
  }

  async function sendTurn(learnerInput: string, options: { replayTeacher?: boolean } = {}) {
    if (!runtimeState.value) {
      throw new Error('Lesson has not started yet')
    }

    const text = learnerInput.trim()
    if (!text) {
      throw new Error('Learner input cannot be empty')
    }

    loading.value = true
    error.value = null
    draftLearnerInput.value = ''

    transcript.value.push(buildTranscriptEntry({
      speaker: 'learner',
      text,
    }))

    try {
      const result = await sendLessonRequest({
        page_uid: selectedPageUid.value,
        student_id: studentId.value.trim() || 'demo-student',
        learner_input: text,
        state: runtimeState.value,
      })
      applyTurnResult(result)
      if (options.replayTeacher !== false) {
        queueTeacherPromptReplay(result.teacher_response, 'lesson-turn')
      }
      return result
    }
    catch (caughtError) {
      const message = caughtError instanceof Error ? caughtError.message : 'Failed to continue lesson'
      error.value = message
      transcript.value.push(buildTranscriptEntry({
        speaker: 'system',
        text: message,
      }))
      throw caughtError
    }
    finally {
      loading.value = false
    }
  }

  async function requestHint() {
    return await sendTurn('help me')
  }

  async function returnToMainline() {
    return await sendTurn(runtimeState.value?.branch_active ? 'okay' : '继续')
  }

  function repeatTeacherPrompt() {
    const text = latestTeacherLine.value.trim()
    if (!text) {
      return
    }

    transcript.value.push(buildTranscriptEntry({
      speaker: 'teacher',
      text,
      local_only: true,
      turn_label: activeTurn.value?.turn_label,
      teaching_action: activeTurn.value?.teaching_action,
      retrieval_mode: activeTurn.value?.retrieval_mode,
      evaluation: activeTurn.value?.evaluation,
    }))
    void replayTeacherPrompt(text, 'lesson-repeat')
  }

  ensureCatalogSelection(preferredPageUid.value || selectedPageUid.value)

  return {
    catalogOutline,
    availablePages,
    scopedPages,
    selectedPageUid,
    selectedGrade,
    selectedSemester,
    selectedUnit,
    studentId,
    draftLearnerInput,
    loading,
    error,
    runtimeState,
    activeTurn,
    transcript,
    catalogLoaded,
    activeTurnClientId,
    apiBaseUrl,
    apiCatalogUrl,
    apiTurnUrl,
    apiTurnStreamUrl,
    isConfigured,
    catalogScopeCount,
    catalogPageCount,
    catalogCoverageLabel,
    catalogCoverageBadges,
    hasStarted,
    currentTeacherPrompt,
    currentPageTitle,
    currentActivityLabel,
    pedagogyProgress,
    latestTeacherLine,
    selectedScope,
    selectedScopeLabel,
    gradeOptions,
    semesterOptions,
    unitOptions,
    loadCatalog,
    setSelectedPageUid,
    selectLessonGrade,
    selectLessonSemester,
    selectLessonGradeSemester,
    selectLessonUnit,
    selectLessonPage,
    setStudentId,
    setDraftLearnerInput,
    appendDraftLearnerInput,
    resetLessonState,
    exportRuntimeSnapshot,
    restoreRuntimeSnapshot,
    beginStreamedTurn,
    applyStreamedTurnResult,
    failStreamedTurn,
    completeStreamedTurn,
    abortActiveTurn,
    isActiveLessonTurn,
    startLesson,
    sendTurn,
    requestHint,
    returnToMainline,
    repeatTeacherPrompt,
  }
})
