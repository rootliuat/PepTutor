import type { ChatHistoryItem } from '../types/chat'
import type { ChatSessionMeta, ChatSessionRecord } from '../types/chat-session'
import type { LessonRuntimeSnapshot } from './lesson'

import { nanoid } from 'nanoid'
import { defineStore, storeToRefs } from 'pinia'
import { computed, ref, watch } from 'vue'

import { createPepTutorLessonSessionSystemPrompt, PEPTUTOR_TEACHER_SESSION_CHARACTER_ID } from '../constants/peptutor-teacher-card'
import { useChatSessionStore } from './chat/session-store'
import { useLessonStore } from './lesson'
import { fetchPepTutorBackend } from './peptutor-backend-auth'

export interface LessonChatHistorySessionSummary {
  session_id?: unknown
  user_id?: unknown
  student_id?: unknown
  character_id?: unknown
  title?: unknown
  preview?: unknown
  created_at?: unknown
  updated_at?: unknown
  active?: unknown
  page_uid?: unknown
  message_count?: unknown
  history_format?: unknown
  audit_status?: unknown
  audit_reason?: unknown
  audit_warnings?: unknown
  message_page_ownership?: unknown
  restore_safety?: unknown
  safe_to_migrate?: unknown
  history_access?: unknown
}

const lessonSessionSnapshotStoragePrefix = 'peptutor/lesson/chat-session-runtime/v1/'
export const lessonActiveTabLeaseStorageKey = 'peptutor/lesson/active-tab-lease/v1'
export const lessonActiveTabLeaseStorageKeyPrefix = 'peptutor/lesson/active-tab-lease/v2/'
const lessonActiveTabIdStorageKey = 'peptutor/lesson/tab-id/v1'
export const lessonActiveTabLeaseTtlMs = 12_000
const lessonActiveTabLeaseHeartbeatMs = 4_000
const lessonTabInactiveWarning = '另一个 lesson 标签页正在接管课堂写入；当前标签页只读，避免重复开课和污染历史。'

export type LessonChatHistoryAccess = 'continue' | 'view_only' | 'read_only'

export interface LessonActiveTabLease {
  tabId: string
  updatedAt: number
  characterId?: string
  pageUid?: string
  studentId?: string
}

export interface LessonChatHistorySafety {
  sessionId: string
  access: LessonChatHistoryAccess
  label: string
  detail: string
  canRestore: boolean
  historyFormat: string
  auditStatus: string
  restoreSafety: string
  messagePageOwnership: string
  safeToMigrate: boolean
  warnings: string[]
}

export interface LessonHistoryIdentity {
  pageUid: string
  studentId: string
}

function cloneJson<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

function messageRole(message: ChatHistoryItem | Record<string, unknown>) {
  return typeof message.role === 'string' ? message.role : ''
}

function isVisibleLessonMessage(message: ChatHistoryItem | Record<string, unknown>) {
  return ['assistant', 'user', 'error', 'tool'].includes(messageRole(message))
}

function normalizeRawChatMessage(message: ChatHistoryItem | Record<string, unknown>, index: number): ChatHistoryItem | null {
  if (!isVisibleLessonMessage(message)) {
    return null
  }

  const { context: _context, ...rest } = message as Record<string, unknown>
  const normalized = cloneJson(rest) as unknown as ChatHistoryItem
  normalized.id = typeof normalized.id === 'string' && normalized.id.trim()
    ? normalized.id.trim()
    : nanoid()
  normalized.createdAt = typeof normalized.createdAt === 'number'
    ? normalized.createdAt
    : Date.now() + index
  return normalized
}

function normalizeRawChatMessages(messages: unknown): ChatHistoryItem[] {
  if (!Array.isArray(messages)) {
    return []
  }

  return messages.flatMap((message, index) => {
    if (!message || typeof message !== 'object') {
      return []
    }

    const normalized = normalizeRawChatMessage(message as Record<string, unknown>, index)
    return normalized ? [normalized] : []
  })
}

function stringValue(value: unknown) {
  return typeof value === 'string' ? value.trim() : ''
}

function leaseKeyPart(value: string, fallback: string) {
  const normalized = value.trim() || fallback
  return encodeURIComponent(normalized)
}

export function lessonActiveTabLeaseStorageKeyForIdentity(identity: LessonHistoryIdentity) {
  return [
    lessonActiveTabLeaseStorageKeyPrefix,
    leaseKeyPart(PEPTUTOR_TEACHER_SESSION_CHARACTER_ID, 'lesson'),
    '/',
    leaseKeyPart(identity.studentId, 'demo-student'),
    '/',
    leaseKeyPart(identity.pageUid, 'unknown-page'),
  ].join('')
}

function stringListValue(value: unknown) {
  if (!Array.isArray(value)) {
    return []
  }
  return value.filter(item => typeof item === 'string' && item.trim()).map(item => item.trim())
}

export function parseLessonActiveTabLease(value: unknown): LessonActiveTabLease | null {
  let candidate = value
  if (typeof value === 'string') {
    try {
      candidate = JSON.parse(value) as unknown
    }
    catch {
      return null
    }
  }

  if (!candidate || typeof candidate !== 'object') {
    return null
  }

  const lease = candidate as Record<string, unknown>
  const tabId = stringValue(lease.tabId)
  const updatedAt = typeof lease.updatedAt === 'number' && Number.isFinite(lease.updatedAt)
    ? lease.updatedAt
    : 0
  if (!tabId || updatedAt <= 0) {
    return null
  }

  const parsed: LessonActiveTabLease = { tabId, updatedAt }
  const characterId = stringValue(lease.characterId)
  const pageUid = stringValue(lease.pageUid)
  const studentId = stringValue(lease.studentId)
  if (characterId) {
    parsed.characterId = characterId
  }
  if (pageUid) {
    parsed.pageUid = pageUid
  }
  if (studentId) {
    parsed.studentId = studentId
  }
  return parsed
}

export function isLessonActiveTabLeaseAvailable(
  lease: LessonActiveTabLease | null,
  tabId: string,
  now: number = Date.now(),
) {
  if (!lease) {
    return true
  }
  return lease.tabId === tabId || now - lease.updatedAt > lessonActiveTabLeaseTtlMs
}

function resolveLessonActiveTabId() {
  if (typeof sessionStorage === 'undefined') {
    return nanoid()
  }

  try {
    const existing = sessionStorage.getItem(lessonActiveTabIdStorageKey)
    if (existing?.trim()) {
      return existing.trim()
    }
    const next = nanoid()
    sessionStorage.setItem(lessonActiveTabIdStorageKey, next)
    return next
  }
  catch {
    return nanoid()
  }
}

function normalizeHistoryAccess(value: unknown): LessonChatHistoryAccess | '' {
  if (value === 'continue' || value === 'view_only' || value === 'read_only') {
    return value
  }
  return ''
}

function roleFromDialogueEntry(entry: Record<string, unknown>): ChatHistoryItem['role'] | null {
  const role = typeof entry.role === 'string' ? entry.role : ''
  if (role === 'assistant' || role === 'user' || role === 'error') {
    return role
  }

  const speaker = typeof entry.speaker === 'string' ? entry.speaker : ''
  if (speaker.includes('学生')) {
    return 'user'
  }
  if (speaker.includes('米粒') || speaker.toLowerCase().includes('teacher')) {
    return 'assistant'
  }
  if (speaker.includes('系统')) {
    return 'error'
  }
  return null
}

export function resolveLessonChatMessageText(message: ChatHistoryItem): string {
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

export function messagesFromHistoryDialogue(dialogue: unknown): ChatHistoryItem[] {
  if (!Array.isArray(dialogue)) {
    return []
  }

  return dialogue.flatMap((entry, index) => {
    if (!entry || typeof entry !== 'object') {
      return []
    }

    const item = entry as Record<string, unknown>
    const role = roleFromDialogueEntry(item)
    const text = typeof item.text === 'string' ? item.text.trim() : ''
    if (!role || !text) {
      return []
    }

    return [{
      role,
      content: text,
      slices: [{ type: 'text', text }],
      tool_results: [],
      createdAt: typeof item.created_at === 'number' ? item.created_at : Date.now() + index,
      id: typeof item.id === 'string' && item.id.trim() ? item.id.trim() : nanoid(),
    } as ChatHistoryItem]
  })
}

export function lessonRuntimeSnapshotFromHistoryPayload(payload: unknown): LessonRuntimeSnapshot | null {
  if (!payload || typeof payload !== 'object') {
    return null
  }

  const historyPayload = payload as {
    metadata?: Record<string, unknown>
    runtime_snapshot?: unknown
    restore_snapshot?: unknown
  }
  const metadata = historyPayload.metadata
  const metadataStudentId = typeof metadata?.student_id === 'string' && metadata.student_id.trim()
    ? metadata.student_id.trim()
    : ''
  const metadataUserId = typeof metadata?.user_id === 'string' && metadata.user_id.trim()
    ? metadata.user_id.trim()
    : ''
  const snapshot = (historyPayload.runtime_snapshot || historyPayload.restore_snapshot) as Partial<LessonRuntimeSnapshot> | null | undefined
  if (snapshot?.version === 1) {
    const snapshotStudentId = typeof snapshot.studentId === 'string' && snapshot.studentId.trim()
      ? snapshot.studentId.trim()
      : ''
    return {
      version: 1,
      selectedPageUid: typeof snapshot.selectedPageUid === 'string' ? snapshot.selectedPageUid : '',
      studentId: snapshotStudentId || metadataStudentId || metadataUserId || 'demo-student',
      runtimeState: snapshot.runtimeState ?? null,
      activeTurn: snapshot.activeTurn ?? null,
      transcript: Array.isArray(snapshot.transcript) ? snapshot.transcript : [],
      updatedAt: typeof snapshot.updatedAt === 'number' ? snapshot.updatedAt : Date.now(),
    }
  }

  const pageUid = typeof metadata?.page_uid === 'string' ? metadata.page_uid.trim() : ''
  if (!pageUid) {
    return null
  }

  return {
    version: 1,
    selectedPageUid: pageUid,
    studentId: metadataStudentId || metadataUserId || 'demo-student',
    runtimeState: null,
    activeTurn: null,
    transcript: [],
    updatedAt: typeof metadata?.updated_at === 'number' ? metadata.updated_at : Date.now(),
  }
}

export function lessonRuntimeSnapshotPageUid(snapshot: LessonRuntimeSnapshot | null) {
  return snapshot?.runtimeState?.current_page_uid?.trim()
    || snapshot?.selectedPageUid?.trim()
    || ''
}

export function lessonRuntimeSnapshotStudentId(snapshot: LessonRuntimeSnapshot | null) {
  return snapshot?.runtimeState?.student_id?.trim()
    || snapshot?.studentId?.trim()
    || ''
}

export function lessonRuntimeSnapshotMatchesIdentity(
  snapshot: LessonRuntimeSnapshot | null,
  identity: LessonHistoryIdentity,
) {
  const pageUid = identity.pageUid.trim()
  const studentId = identity.studentId.trim()
  const snapshotPageUid = lessonRuntimeSnapshotPageUid(snapshot)
  const snapshotStudentId = lessonRuntimeSnapshotStudentId(snapshot)

  return Boolean(
    snapshot
    && (!pageUid || snapshotPageUid === pageUid)
    && (!studentId || snapshotStudentId === studentId),
  )
}

export function lessonChatHistoryRecordFromPayload(payload: unknown): ChatSessionRecord | null {
  if (!payload || typeof payload !== 'object') {
    return null
  }

  const historyPayload = payload as {
    format?: unknown
    metadata?: Record<string, unknown>
    messages?: unknown
    dialogue?: unknown
    raw_chat_session?: Record<string, unknown>
  }
  const metadata = historyPayload.metadata
  const format = historyPayload.format
  if (
    (format !== 'peptutor-chat-history:v1' && format !== 'peptutor-chat-history:v2' && format !== 'peptutor-chat-history:v3')
    || !metadata
  ) {
    return null
  }

  const sessionId = typeof metadata.session_id === 'string' ? metadata.session_id.trim() : ''
  if (!sessionId) {
    return null
  }

  const rawMessages = format === 'peptutor-chat-history:v3'
    ? normalizeRawChatMessages(historyPayload.raw_chat_session?.messages)
    : []
  const historyMessages = rawMessages.length > 0
    ? rawMessages
    : format === 'peptutor-chat-history:v2'
      ? messagesFromHistoryDialogue(historyPayload.dialogue)
      : normalizeRawChatMessages(historyPayload.messages)

  return {
    meta: {
      sessionId,
      userId: typeof metadata.user_id === 'string' && metadata.user_id.trim() ? metadata.user_id.trim() : 'local',
      characterId: typeof metadata.character_id === 'string' && metadata.character_id.trim()
        ? metadata.character_id.trim()
        : PEPTUTOR_TEACHER_SESSION_CHARACTER_ID,
      title: typeof metadata.title === 'string' && metadata.title.trim() ? metadata.title.trim() : undefined,
      createdAt: typeof metadata.created_at === 'number' ? metadata.created_at : Date.now(),
      updatedAt: typeof metadata.updated_at === 'number' ? metadata.updated_at : Date.now(),
    },
    messages: historyMessages,
  }
}

export function lessonChatHistoryMetaFromSummary(summary: LessonChatHistorySessionSummary): ChatSessionMeta | null {
  const sessionId = typeof summary.session_id === 'string' ? summary.session_id.trim() : ''
  if (!sessionId) {
    return null
  }

  const title = typeof summary.title === 'string' && summary.title.trim()
    ? summary.title.trim()
    : typeof summary.preview === 'string' && summary.preview.trim()
      ? summary.preview.trim()
      : undefined

  return {
    sessionId,
    userId: typeof summary.user_id === 'string' && summary.user_id.trim() ? summary.user_id.trim() : 'local',
    characterId: typeof summary.character_id === 'string' && summary.character_id.trim()
      ? summary.character_id.trim()
      : PEPTUTOR_TEACHER_SESSION_CHARACTER_ID,
    title,
    createdAt: typeof summary.created_at === 'number' ? summary.created_at : Date.now(),
    updatedAt: typeof summary.updated_at === 'number' ? summary.updated_at : Date.now(),
  }
}

export function lessonChatHistorySafetyFromSummary(summary: LessonChatHistorySessionSummary): LessonChatHistorySafety | null {
  const sessionId = stringValue(summary.session_id)
  if (!sessionId) {
    return null
  }

  const historyFormat = stringValue(summary.history_format)
  const auditStatus = stringValue(summary.audit_status)
  const restoreSafety = stringValue(summary.restore_safety)
  const messagePageOwnership = stringValue(summary.message_page_ownership)
  const safeToMigrate = summary.safe_to_migrate === true
  const warnings = stringListValue(summary.audit_warnings)

  const fallbackAccess: LessonChatHistoryAccess = historyFormat === 'peptutor-chat-history:v3'
    && auditStatus === 'clean'
    && restoreSafety === 'block'
    ? 'continue'
    : auditStatus === 'legacy_readonly' || auditStatus === 'repairable'
      ? 'read_only'
      : 'view_only'
  const access = normalizeHistoryAccess(summary.history_access) || fallbackAccess
  if (access === 'continue') {
    return {
      sessionId,
      access,
      label: '可继续',
      detail: '可恢复到原课堂 block',
      canRestore: true,
      historyFormat,
      auditStatus,
      restoreSafety,
      messagePageOwnership,
      safeToMigrate,
      warnings,
    }
  }

  if (access === 'read_only') {
    return {
      sessionId,
      access,
      label: '只读',
      detail: '旧历史或混页历史，只读查看',
      canRestore: false,
      historyFormat,
      auditStatus,
      restoreSafety,
      messagePageOwnership,
      safeToMigrate,
      warnings,
    }
  }

  return {
    sessionId,
    access,
    label: '不可恢复',
    detail: '可查看聊天，但不能恢复课堂状态',
    canRestore: false,
    historyFormat,
    auditStatus,
    restoreSafety,
    messagePageOwnership,
    safeToMigrate,
    warnings,
  }
}

export const useLessonChatHistoryStore = defineStore('lesson-chat-history', () => {
  const lessonStore = useLessonStore()
  const chatSessionStore = useChatSessionStore()
  const { activeSessionId, messages } = storeToRefs(chatSessionStore)

  const listLoading = ref(false)
  const sessionLoading = ref(false)
  const syncInFlight = ref(false)
  const switchingSession = ref(false)
  const listError = ref('')
  const sessionError = ref('')
  const syncError = ref('')
  const restoreWarning = ref('')
  const historySafetyBySessionId = ref<Record<string, LessonChatHistorySafety>>({})
  const activeLessonTabId = ref(resolveLessonActiveTabId())
  const activeLessonTabWritable = ref(typeof window === 'undefined')

  const serverSessionIds = new Set<string>()
  const hydratedSessionIds = new Set<string>()
  let serverHistoryListLoaded = false
  let serverHistoryIdentityKey = ''
  let initialized = false
  let initializePromise: Promise<void> | null = null
  let syncTimeout: ReturnType<typeof setTimeout> | undefined
  let syncQueue = Promise.resolve()
  let pagehideRegistered = false
  let activeLessonTabLeaseRegistered = false
  let activeLessonTabHeartbeat: ReturnType<typeof setInterval> | undefined
  let activeLessonTabLeaseKey = ''
  let pageEntrySessionPromise: Promise<void> | null = null

  const lessonSessionSystemPrompt = computed(() => createPepTutorLessonSessionSystemPrompt())
  const fileSyncEnabled = computed(() =>
    import.meta.env.MODE !== 'test' && Boolean(lessonStore.apiBaseUrl),
  )
  const syncUrl = computed(() =>
    lessonStore.apiBaseUrl ? `${lessonStore.apiBaseUrl}/lesson/chat-history/session` : '',
  )
  const sessionsUrl = computed(() => {
    if (!lessonStore.apiBaseUrl) {
      return ''
    }

    const params = new URLSearchParams()
    params.set('character_id', PEPTUTOR_TEACHER_SESSION_CHARACTER_ID)
    const studentId = currentLessonStudentId()
    const pageUid = currentLessonPageUid()
    if (studentId) {
      params.set('student_id', studentId)
    }
    if (pageUid) {
      params.set('page_uid', pageUid)
    }
    return `${lessonStore.apiBaseUrl}/lesson/chat-history/sessions?${params.toString()}`
  })
  const visibleMessages = computed(() =>
    (messages.value as ChatHistoryItem[]).filter(isVisibleLessonMessage),
  )
  const activeLessonTabReadOnly = computed(() => !activeLessonTabWritable.value)

  function setLessonTabInactiveWarning() {
    if (!restoreWarning.value || restoreWarning.value === lessonTabInactiveWarning) {
      restoreWarning.value = lessonTabInactiveWarning
    }
  }

  function clearLessonTabInactiveWarning() {
    if (restoreWarning.value === lessonTabInactiveWarning) {
      restoreWarning.value = ''
    }
  }

  function currentLessonPageUid() {
    return lessonStore.selectedPageUid?.trim()
      || lessonStore.runtimeState?.current_page_uid?.trim()
      || ''
  }

  function currentLessonStudentId() {
    return lessonStore.studentId?.trim()
      || lessonStore.runtimeState?.student_id?.trim()
      || 'demo-student'
  }

  function activeRuntimeMatchesCurrentLessonIdentity() {
    const runtimeState = lessonStore.runtimeState
    if (!runtimeState) {
      return false
    }

    return runtimeState.current_page_uid?.trim() === currentLessonPageUid()
      && (runtimeState.student_id?.trim() || 'demo-student') === currentLessonStudentId()
  }

  function currentLeaseIdentity(): LessonHistoryIdentity {
    return {
      pageUid: currentLessonPageUid(),
      studentId: currentLessonStudentId(),
    }
  }

  function currentHistoryIdentityKey() {
    return `${currentLessonStudentId()}::${currentLessonPageUid()}`
  }

  function currentActiveLessonTabLeaseKey() {
    return lessonActiveTabLeaseStorageKeyForIdentity(currentLeaseIdentity())
  }

  function readActiveLessonTabLease(key: string = currentActiveLessonTabLeaseKey()) {
    if (typeof localStorage === 'undefined') {
      return null
    }

    try {
      return parseLessonActiveTabLease(localStorage.getItem(key))
    }
    catch {
      return null
    }
  }

  function writeActiveLessonTabLease() {
    const identity = currentLeaseIdentity()
    const leaseKey = currentActiveLessonTabLeaseKey()
    if (typeof localStorage === 'undefined') {
      activeLessonTabWritable.value = true
      activeLessonTabLeaseKey = leaseKey
      clearLessonTabInactiveWarning()
      return true
    }

    try {
      if (activeLessonTabLeaseKey && activeLessonTabLeaseKey !== leaseKey) {
        releaseActiveLessonTabLease(activeLessonTabLeaseKey)
      }
      localStorage.setItem(
        leaseKey,
        JSON.stringify({
          tabId: activeLessonTabId.value,
          updatedAt: Date.now(),
          characterId: PEPTUTOR_TEACHER_SESSION_CHARACTER_ID,
          pageUid: identity.pageUid,
          studentId: identity.studentId,
        } satisfies LessonActiveTabLease),
      )
      activeLessonTabLeaseKey = leaseKey
      activeLessonTabWritable.value = true
      clearLessonTabInactiveWarning()
      return true
    }
    catch {
      activeLessonTabWritable.value = true
      activeLessonTabLeaseKey = leaseKey
      clearLessonTabInactiveWarning()
      return true
    }
  }

  function takeActiveLessonTabLease() {
    const lease = readActiveLessonTabLease()
    if (
      typeof document !== 'undefined'
      && document.hidden
      && !isLessonActiveTabLeaseAvailable(lease, activeLessonTabId.value)
    ) {
      activeLessonTabWritable.value = false
      setLessonTabInactiveWarning()
      return false
    }

    return writeActiveLessonTabLease()
  }

  function refreshActiveLessonTabWritable() {
    if (typeof localStorage === 'undefined') {
      activeLessonTabWritable.value = true
      activeLessonTabLeaseKey = currentActiveLessonTabLeaseKey()
      clearLessonTabInactiveWarning()
      return true
    }

    const leaseKey = currentActiveLessonTabLeaseKey()
    const lease = readActiveLessonTabLease(leaseKey)
    if (isLessonActiveTabLeaseAvailable(lease, activeLessonTabId.value)) {
      return writeActiveLessonTabLease()
    }

    const isWritable = Boolean(
      lease
      && lease.tabId === activeLessonTabId.value
      && Date.now() - lease.updatedAt <= lessonActiveTabLeaseTtlMs,
    )
    activeLessonTabWritable.value = isWritable
    if (isWritable) {
      activeLessonTabLeaseKey = leaseKey
      clearLessonTabInactiveWarning()
    }
    else {
      setLessonTabInactiveWarning()
    }
    return isWritable
  }

  function activeLessonTabCanWrite() {
    return activeLessonTabWritable.value && refreshActiveLessonTabWritable()
  }

  function renewActiveLessonTabLease() {
    if (!activeLessonTabWritable.value) {
      return
    }

    const lease = readActiveLessonTabLease(activeLessonTabLeaseKey || currentActiveLessonTabLeaseKey())
    if (typeof localStorage !== 'undefined' && lease?.tabId !== activeLessonTabId.value) {
      activeLessonTabWritable.value = false
      setLessonTabInactiveWarning()
      return
    }

    writeActiveLessonTabLease()
  }

  function releaseActiveLessonTabLease(key: string = activeLessonTabLeaseKey || currentActiveLessonTabLeaseKey()) {
    if (typeof localStorage === 'undefined') {
      return
    }

    const lease = readActiveLessonTabLease(key)
    if (lease?.tabId !== activeLessonTabId.value) {
      return
    }

    try {
      localStorage.removeItem(key)
      if (activeLessonTabLeaseKey === key) {
        activeLessonTabLeaseKey = ''
      }
    }
    catch {
    }
  }

  function handleActiveLessonTabLeaseChanged() {
    refreshActiveLessonTabWritable()
  }

  function registerActiveLessonTabLease() {
    if (activeLessonTabLeaseRegistered || typeof window === 'undefined') {
      return
    }

    activeLessonTabLeaseRegistered = true
    window.addEventListener('storage', (event) => {
      if (
        event.key === lessonActiveTabLeaseStorageKey
        || event.key === currentActiveLessonTabLeaseKey()
        || event.key?.startsWith(lessonActiveTabLeaseStorageKeyPrefix)
      ) {
        handleActiveLessonTabLeaseChanged()
      }
    })
    window.addEventListener('focus', () => {
      takeActiveLessonTabLease()
    })
    if (typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', () => {
        if (!document.hidden) {
          takeActiveLessonTabLease()
        }
      })
    }
    if (!activeLessonTabHeartbeat) {
      activeLessonTabHeartbeat = setInterval(renewActiveLessonTabLease, lessonActiveTabLeaseHeartbeatMs)
    }
  }

  function snapshotKey(sessionId: string) {
    return `${lessonSessionSnapshotStoragePrefix}${sessionId}`
  }

  function readLessonSessionSnapshot(sessionId: string): LessonRuntimeSnapshot | null {
    if (typeof localStorage === 'undefined' || !sessionId) {
      return null
    }

    try {
      const raw = localStorage.getItem(snapshotKey(sessionId))
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
      localStorage.setItem(snapshotKey(sessionId), JSON.stringify(snapshot))
    }
    catch {
    }
  }

  function persistActiveRuntimeSnapshot() {
    if (
      switchingSession.value
      || !activeSessionId.value
      || activeHistoryIsReadOnly()
      || activeSessionConflictsWithCurrentLessonPage()
    ) {
      return
    }

    writeLessonSessionSnapshot(activeSessionId.value, lessonStore.exportRuntimeSnapshot())
  }

  function visibleMessagesForSession(sessionId: string) {
    return chatSessionStore.getSessionMessages(sessionId, {
      systemPrompt: lessonSessionSystemPrompt.value,
    }).filter(isVisibleLessonMessage)
  }

  function hasVisibleConversationMessages(sessionId: string) {
    return visibleMessagesForSession(sessionId).some(message =>
      resolveLessonChatMessageText(message).trim(),
    )
  }

  function sessionConflictsWithCurrentLessonPage(sessionId: string) {
    if (!sessionId || !hasVisibleConversationMessages(sessionId)) {
      return false
    }

    const snapshot = readLessonSessionSnapshot(sessionId)
    if (!snapshot) {
      return true
    }

    return !lessonRuntimeSnapshotMatchesIdentity(snapshot, {
      pageUid: currentLessonPageUid(),
      studentId: currentLessonStudentId(),
    })
  }

  function sessionMatchesCurrentLessonIdentity(sessionId: string) {
    const snapshot = readLessonSessionSnapshot(sessionId)
    if (lessonRuntimeSnapshotMatchesIdentity(snapshot, {
      pageUid: currentLessonPageUid(),
      studentId: currentLessonStudentId(),
    })) {
      return true
    }

    return !hasVisibleConversationMessages(sessionId) && !snapshot
  }

  function sessionBelongsToCurrentLessonIdentity(sessionId: string) {
    return sessionMatchesCurrentLessonIdentity(sessionId)
  }

  function activeSessionConflictsWithCurrentLessonPage() {
    return activeSessionId.value
      ? sessionConflictsWithCurrentLessonPage(activeSessionId.value)
      : false
  }

  function findCurrentLessonHistorySession() {
    const matchingSession = chatSessionStore
      .getSessionMetasForCharacter(PEPTUTOR_TEACHER_SESSION_CHARACTER_ID)
      .find(meta =>
        meta.sessionId !== activeSessionId.value
        && canRestoreHistorySession(meta.sessionId)
        && sessionMatchesCurrentLessonIdentity(meta.sessionId)
        && hasVisibleConversationMessages(meta.sessionId),
      )

    return matchingSession?.sessionId || ''
  }

  async function createEmptyCurrentLessonSession() {
    await chatSessionStore.createSession(PEPTUTOR_TEACHER_SESSION_CHARACTER_ID, {
      title: newSessionTitle(),
      systemPrompt: lessonSessionSystemPrompt.value,
    })
  }

  async function ensureCurrentLessonHistorySession() {
    if (switchingSession.value || activeLessonTabReadOnly.value || lessonStore.loading) {
      return
    }

    const pageUid = currentLessonPageUid()
    if (!pageUid) {
      return
    }

    const sessionId = activeSessionId.value
    if (
      sessionId
      && canRestoreHistorySession(sessionId)
      && sessionMatchesCurrentLessonIdentity(sessionId)
    ) {
      return
    }

    switchingSession.value = true
    try {
      const matchingSessionId = findCurrentLessonHistorySession()
      if (matchingSessionId) {
        chatSessionStore.setActiveSession(matchingSessionId, {
          systemPrompt: lessonSessionSystemPrompt.value,
        })
        await chatSessionStore.loadSession(matchingSessionId)
        restoreSnapshotForSession(matchingSessionId)
        return
      }

      if (!activeRuntimeMatchesCurrentLessonIdentity()) {
        lessonStore.resetLessonState({ keepSelectedPage: true })
      }
      await createEmptyCurrentLessonSession()
    }
    finally {
      switchingSession.value = false
    }
  }

  function historySafetyForSession(sessionId: string) {
    return historySafetyBySessionId.value[sessionId] ?? null
  }

  function canRestoreHistorySession(sessionId: string) {
    return historySafetyForSession(sessionId)?.canRestore ?? true
  }

  function activeHistoryIsReadOnly() {
    return activeLessonTabReadOnly.value
      || (activeSessionId.value ? !canRestoreHistorySession(activeSessionId.value) : false)
  }

  const activeHistoryReadOnly = computed(() => activeHistoryIsReadOnly())

  function rawChatMessagesForStorage() {
    return visibleMessages.value.flatMap((message, index) => {
      const normalized = normalizeRawChatMessage(message, index)
      return normalized ? [normalized] : []
    })
  }

  function writeSnapshotFromHistoryPayload(payload: unknown, sessionId: string) {
    const snapshot = lessonRuntimeSnapshotFromHistoryPayload(payload)
    if (snapshot) {
      writeLessonSessionSnapshot(sessionId, snapshot)
    }
    return snapshot
  }

  async function hydrateLessonChatHistoryFiles(options: { force?: boolean } = {}) {
    const identityKey = currentHistoryIdentityKey()
    const identityChanged = serverHistoryIdentityKey !== identityKey
    if (
      !options.force
      && !identityChanged
      && serverHistoryListLoaded
      && fileSyncEnabled.value
      && sessionsUrl.value
    ) {
      return
    }
    if (!fileSyncEnabled.value || !sessionsUrl.value) {
      return
    }

    listLoading.value = true
    listError.value = ''
    const response = await fetchPepTutorBackend(
      sessionsUrl.value,
      { method: 'GET' },
      { retryUnauthorized: false },
    ).catch((error) => {
      listError.value = error instanceof Error ? error.message : '加载历史列表失败'
      return undefined
    })
    listLoading.value = false
    if (!response?.ok) {
      if (response) {
        listError.value = `加载历史列表失败 (${response.status})`
      }
      return
    }

    const summaries = await response.json().catch(() => []) as Array<Record<string, unknown>>
    if (!Array.isArray(summaries)) {
      listError.value = '历史列表格式错误'
      return
    }

    serverHistoryListLoaded = true
    serverHistoryIdentityKey = identityKey
    serverSessionIds.clear()
    const nextSafetyBySessionId = { ...historySafetyBySessionId.value }
    for (const summary of summaries.slice(0, 100)) {
      const meta = lessonChatHistoryMetaFromSummary(summary)
      if (!meta || meta.characterId !== PEPTUTOR_TEACHER_SESSION_CHARACTER_ID) {
        continue
      }

      serverSessionIds.add(meta.sessionId)
      const safety = lessonChatHistorySafetyFromSummary(summary)
      if (safety) {
        nextSafetyBySessionId[meta.sessionId] = safety
      }
      await chatSessionStore.upsertSessionMeta(meta, {
        setActive: false,
      })
    }
    historySafetyBySessionId.value = nextSafetyBySessionId
  }

  async function hydrateLessonHistorySessionFromFile(sessionId: string) {
    if (
      !sessionId
      || hydratedSessionIds.has(sessionId)
      || !fileSyncEnabled.value
      || !lessonStore.apiBaseUrl
      || (serverHistoryListLoaded && !serverSessionIds.has(sessionId))
    ) {
      return
    }

    sessionLoading.value = true
    sessionError.value = ''
    hydratedSessionIds.add(sessionId)
    const params = new URLSearchParams()
    const studentId = currentLessonStudentId()
    const pageUid = currentLessonPageUid()
    params.set('character_id', PEPTUTOR_TEACHER_SESSION_CHARACTER_ID)
    if (studentId) {
      params.set('student_id', studentId)
    }
    if (pageUid) {
      params.set('page_uid', pageUid)
    }
    const filterQuery = params.toString()
    const sessionUrl = `${lessonStore.apiBaseUrl}/lesson/chat-history/sessions/${encodeURIComponent(sessionId)}${filterQuery ? `?${filterQuery}` : ''}`
    const response = await fetchPepTutorBackend(
      sessionUrl,
      { method: 'GET' },
      { retryUnauthorized: false },
    ).catch((error) => {
      sessionError.value = error instanceof Error ? error.message : '加载历史会话失败'
      return undefined
    })
    sessionLoading.value = false
    if (!response?.ok) {
      if (response) {
        sessionError.value = `加载历史会话失败 (${response.status})`
      }
      hydratedSessionIds.delete(sessionId)
      return
    }

    const payload = await response.json().catch(() => null) as unknown
    const record = lessonChatHistoryRecordFromPayload(payload)
    if (!record) {
      sessionError.value = '历史会话格式错误'
      hydratedSessionIds.delete(sessionId)
      return
    }

    await chatSessionStore.upsertSessionRecord(record, {
      setActive: false,
      systemPrompt: lessonSessionSystemPrompt.value,
    })
    writeSnapshotFromHistoryPayload(payload, record.meta.sessionId)
  }

  async function syncCurrentSessionNow(reason: string = 'lesson-history-sync') {
    const sessionId = activeSessionId.value
    const targetSyncUrl = syncUrl.value
    if (
      !fileSyncEnabled.value
      || !sessionId
      || !targetSyncUrl
      || !activeLessonTabCanWrite()
      || activeHistoryIsReadOnly()
      || activeSessionConflictsWithCurrentLessonPage()
    ) {
      return
    }

    const meta = chatSessionStore.sessionMetas[sessionId]
    if (!meta) {
      return
    }

    const rawMessages = rawChatMessagesForStorage()
    if (rawMessages.length === 0) {
      return
    }
    const runtimeSnapshot = lessonStore.exportRuntimeSnapshot()
    if (!runtimeSnapshot.runtimeState) {
      return
    }

    syncInFlight.value = true
    syncError.value = ''
    const response = await fetchPepTutorBackend(targetSyncUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      keepalive: reason === 'pagehide',
      body: JSON.stringify({
        session_id: meta.sessionId,
        user_id: currentLessonStudentId(),
        student_id: currentLessonStudentId(),
        character_id: PEPTUTOR_TEACHER_SESSION_CHARACTER_ID,
        title: meta.title || null,
        created_at: meta.createdAt,
        updated_at: meta.updatedAt,
        active: sessionId === activeSessionId.value,
        page_uid: lessonStore.selectedPageUid || null,
        messages: cloneJson(rawMessages),
        raw_chat_session: {
          messages: cloneJson(rawMessages),
        },
        runtime_snapshot: runtimeSnapshot,
      }),
    }, { retryUnauthorized: false }).catch((error) => {
      syncError.value = error instanceof Error ? error.message : '同步历史失败'
      return undefined
    })
    syncInFlight.value = false

    if (!response?.ok) {
      if (response) {
        syncError.value = `同步历史失败 (${response.status})`
      }
    }
  }

  function queueSyncCurrentSession() {
    if (!fileSyncEnabled.value || !activeLessonTabCanWrite()) {
      return
    }

    if (syncTimeout) {
      clearTimeout(syncTimeout)
    }

    syncTimeout = setTimeout(() => {
      syncTimeout = undefined
      syncQueue = syncQueue
        .catch(() => undefined)
        .then(() => syncCurrentSessionNow())
    }, 500)
  }

  async function flushCurrentSession(reason: string = 'lesson-history-flush') {
    if (syncTimeout) {
      clearTimeout(syncTimeout)
      syncTimeout = undefined
    }

    await syncQueue.catch(() => undefined)
    await syncCurrentSessionNow(reason)
  }

  async function startCurrentLessonSilently() {
    if (!activeLessonTabCanWrite() || !lessonStore.isConfigured || lessonStore.loading || !lessonStore.selectedPageUid) {
      return
    }

    await lessonStore.startLesson(lessonStore.selectedPageUid, { replayTeacher: false })
  }

  function restoreSnapshotForSession(sessionId: string) {
    const snapshot = readLessonSessionSnapshot(sessionId)
    if (!snapshot) {
      restoreWarning.value = '这个历史没有课堂状态，只能查看聊天，不能直接续上原 block。'
      lessonStore.resetLessonState({ keepSelectedPage: true })
      return false
    }

    lessonStore.restoreRuntimeSnapshot(snapshot)
    restoreWarning.value = snapshot.runtimeState
      ? ''
      : '这个历史只有页面信息，没有原 block 状态。'
    return Boolean(snapshot.runtimeState)
  }

  async function createNewLessonSession() {
    takeActiveLessonTabLease()
    await flushCurrentSession('before-new-lesson-session')
    switchingSession.value = true
    restoreWarning.value = ''
    try {
      lessonStore.resetLessonState({ keepSelectedPage: true })
      await chatSessionStore.createSession(PEPTUTOR_TEACHER_SESSION_CHARACTER_ID, {
        title: newSessionTitle(),
        systemPrompt: lessonSessionSystemPrompt.value,
      })
      await startCurrentLessonSilently()
    }
    finally {
      switchingSession.value = false
      syncPageEntryPromptToActiveSession()
      persistActiveRuntimeSnapshot()
      queueSyncCurrentSession()
    }
  }

  async function selectLessonHistorySession(sessionId: string) {
    if (!sessionId) {
      return
    }

    takeActiveLessonTabLease()
    await flushCurrentSession('before-select-lesson-history')
    const canRestore = canRestoreHistorySession(sessionId)
    switchingSession.value = true
    restoreWarning.value = ''
    try {
      await hydrateLessonHistorySessionFromFile(sessionId)
      chatSessionStore.setActiveSession(sessionId, {
        systemPrompt: lessonSessionSystemPrompt.value,
      })
      await chatSessionStore.loadSession(sessionId)
      if (canRestore) {
        restoreSnapshotForSession(sessionId)
      }
      else {
        const safety = historySafetyForSession(sessionId)
        restoreWarning.value = safety?.detail || '这个历史只能查看聊天，不能恢复课堂状态。'
        lessonStore.resetLessonState({ keepSelectedPage: true })
      }
    }
    finally {
      switchingSession.value = false
      if (canRestore) {
        syncPageEntryPromptToActiveSession()
        persistActiveRuntimeSnapshot()
        queueSyncCurrentSession()
      }
    }
  }

  function newSessionTitle() {
    const pageTitle = lessonStore.currentPageTitle?.trim() || lessonStore.selectedPageUid || '课堂'
    try {
      const timeLabel = new Intl.DateTimeFormat('zh-CN', {
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      }).format(new Date())
      return `${pageTitle} · ${timeLabel}`
    }
    catch {
      return pageTitle
    }
  }

  function syncPageEntryPromptToActiveSession() {
    const sessionId = activeSessionId.value
    const pageUid = lessonStore.runtimeState?.current_page_uid?.trim()
    const turnLabel = lessonStore.activeTurn?.turn_label
    const teacherResponse = lessonStore.activeTurn?.teacher_response?.trim()
    if (
      switchingSession.value
      || !sessionId
      || !pageUid
      || turnLabel !== 'page_entry'
      || !teacherResponse
      || !activeLessonTabCanWrite()
      || activeHistoryIsReadOnly()
    ) {
      return
    }

    if (sessionConflictsWithCurrentLessonPage(sessionId)) {
      void createCurrentPageEntrySession(teacherResponse)
      return
    }

    if (hasVisibleConversationMessages(sessionId)) {
      return
    }

    const existingMessages = chatSessionStore.getSessionMessages(sessionId, {
      systemPrompt: lessonSessionSystemPrompt.value,
    })
    const systemMessages = existingMessages.filter(message => message.role === 'system')
    const assistantMessage: ChatHistoryItem = {
      role: 'assistant',
      content: teacherResponse,
      slices: [{ type: 'text', text: teacherResponse }],
      tool_results: [],
      createdAt: Date.now(),
      id: nanoid(),
    }
    chatSessionStore.setSessionMessages(sessionId, [...systemMessages, assistantMessage])
    queueSyncCurrentSession()
  }

  async function createCurrentPageEntrySession(teacherResponse: string) {
    if (!activeLessonTabCanWrite()) {
      return
    }

    if (pageEntrySessionPromise) {
      return pageEntrySessionPromise
    }

    pageEntrySessionPromise = (async () => {
      switchingSession.value = true
      try {
        const sessionId = await chatSessionStore.createSession(PEPTUTOR_TEACHER_SESSION_CHARACTER_ID, {
          title: newSessionTitle(),
          systemPrompt: lessonSessionSystemPrompt.value,
        })
        const existingMessages = chatSessionStore.getSessionMessages(sessionId, {
          systemPrompt: lessonSessionSystemPrompt.value,
        })
        const systemMessages = existingMessages.filter(message => message.role === 'system')
        const assistantMessage: ChatHistoryItem = {
          role: 'assistant',
          content: teacherResponse,
          slices: [{ type: 'text', text: teacherResponse }],
          tool_results: [],
          createdAt: Date.now(),
          id: nanoid(),
        }
        chatSessionStore.setSessionMessages(sessionId, [...systemMessages, assistantMessage])
        writeLessonSessionSnapshot(sessionId, lessonStore.exportRuntimeSnapshot())
      }
      finally {
        switchingSession.value = false
        pageEntrySessionPromise = null
      }

      persistActiveRuntimeSnapshot()
      queueSyncCurrentSession()
    })()

    return pageEntrySessionPromise
  }

  function registerPagehideFlush() {
    if (pagehideRegistered || typeof window === 'undefined') {
      return
    }

    pagehideRegistered = true
    window.addEventListener('pagehide', () => {
      void flushCurrentSession('pagehide').finally(() => {
        releaseActiveLessonTabLease()
      })
    })
  }

  async function initialize() {
    registerActiveLessonTabLease()
    takeActiveLessonTabLease()

    if (initialized) {
      registerPagehideFlush()
      syncPageEntryPromptToActiveSession()
      queueSyncCurrentSession()
      return
    }
    if (initializePromise) {
      return initializePromise
    }

    initializePromise = (async () => {
      await chatSessionStore.initialize()
      await chatSessionStore.ensureActiveSessionForCharacter(PEPTUTOR_TEACHER_SESSION_CHARACTER_ID, {
        systemPrompt: lessonSessionSystemPrompt.value,
        title: '米粒老师课堂',
      })
      await hydrateLessonChatHistoryFiles()

      await ensureCurrentLessonHistorySession()

      let sessionId = activeSessionId.value
      if (sessionId) {
        await hydrateLessonHistorySessionFromFile(sessionId)
        await ensureCurrentLessonHistorySession()
        sessionId = activeSessionId.value

        if (sessionId && hasVisibleConversationMessages(sessionId)) {
          const snapshot = readLessonSessionSnapshot(sessionId)
          const currentPageUid = lessonStore.selectedPageUid?.trim() || ''
          const currentStudentId = lessonStore.studentId?.trim() || ''
          if (
            !activeHistoryIsReadOnly()
            && snapshot?.runtimeState
            && lessonRuntimeSnapshotMatchesIdentity(snapshot, {
              pageUid: currentPageUid,
              studentId: currentStudentId,
            })
          ) {
            lessonStore.restoreRuntimeSnapshot(snapshot)
          }
          else if (activeHistoryIsReadOnly()) {
            restoreWarning.value = historySafetyForSession(sessionId)?.detail || '这个历史只能查看聊天，不能恢复课堂状态。'
          }
        }
      }

      registerPagehideFlush()
      syncPageEntryPromptToActiveSession()
      queueSyncCurrentSession()
      initialized = true
    })()

    try {
      await initializePromise
    }
    finally {
      initializePromise = null
    }
  }

  watch(
    () => [
      lessonStore.selectedPageUid,
      lessonStore.studentId,
    ] as const,
    () => {
      if (!initialized || switchingSession.value) {
        return
      }

      takeActiveLessonTabLease()
      void hydrateLessonChatHistoryFiles({ force: true })
        .finally(() => ensureCurrentLessonHistorySession())
    },
    { flush: 'post' },
  )

  watch(
    () => lessonStore.loading,
    (loading) => {
      if (!initialized || loading || switchingSession.value) {
        return
      }

      void ensureCurrentLessonHistorySession()
    },
    { flush: 'post' },
  )

  watch(
    () => [
      activeSessionId.value,
      lessonStore.runtimeState?.current_page_uid,
      lessonStore.activeTurn?.turn_label,
      lessonStore.activeTurn?.block_uid,
      lessonStore.activeTurn?.teacher_response,
    ] as const,
    syncPageEntryPromptToActiveSession,
    { immediate: true },
  )

  watch(
    () => [
      activeSessionId.value,
      lessonStore.selectedPageUid,
      lessonStore.runtimeState,
      lessonStore.activeTurn,
      lessonStore.transcript,
      messages.value,
    ] as const,
    () => {
      persistActiveRuntimeSnapshot()
      queueSyncCurrentSession()
    },
    { deep: true, flush: 'post' },
  )

  return {
    listLoading,
    sessionLoading,
    syncInFlight,
    switchingSession,
    listError,
    sessionError,
    syncError,
    restoreWarning,
    historySafetyBySessionId,
    activeLessonTabWritable,
    activeLessonTabReadOnly,
    activeHistoryReadOnly,
    visibleMessages,
    initialize,
    hydrateLessonChatHistoryFiles,
    hydrateLessonHistorySessionFromFile,
    queueSyncCurrentSession,
    flushCurrentSession,
    createNewLessonSession,
    selectLessonHistorySession,
    ensureCurrentLessonHistorySession,
    persistActiveRuntimeSnapshot,
    readLessonSessionSnapshot,
    historySafetyForSession,
    canRestoreHistorySession,
    sessionBelongsToCurrentLessonIdentity,
  }
})
