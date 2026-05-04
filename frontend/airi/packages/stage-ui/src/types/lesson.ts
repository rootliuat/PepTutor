export type LessonEvaluationResult
  = | 'correct'
    | 'acceptable'
    | 'partially_correct'
    | 'incorrect'
    | 'off_topic'
    | 'unclear'

export type LessonTurnLabel
  = | 'page_entry'
    | 'answer_question'
    | 'ask_knowledge'
    | 'ask_help'
    | 'navigation'
    | 'social'

export type LessonTeachingAction
  = | 'page_intro'
    | 'probe'
    | 'confirm'
    | 'hint'
    | 'model'
    | 'repeat_drill'
    | 'explain'
    | 'redirect'
    | 'complete'

export type LessonRetrievalMode = 'none' | 'block' | 'page' | 'unit' | 'branch'

export type LessonActivityType
  = | 'page_entry'
    | 'teaching'
    | 'practice'
    | 'review'
    | 'branch'

export interface LessonRuntimeState {
  student_id: string
  current_grade: string
  current_semester: string
  current_unit: string
  current_page: number
  current_page_uid: string
  current_page_type: string
  current_block_uid: string | null
  current_activity_type: LessonActivityType
  awaiting_answer: boolean
  last_teacher_question: string | null
  hint_level: number
  pedagogy_level: number
  page_entry_probe_done: boolean
  repair_mode: string
  recent_turn_labels: string[]
  same_goal_attempt_count: number
  last_eval_result: LessonEvaluationResult | null
  model_already_given: boolean
  branch_active: boolean
  branch_reason: string | null
  branch_origin_block_uid: string | null
  branch_turn_budget: number | null
  return_anchor: string | null
  return_target: string | null
  simplemem_content_session_id: string | null
  simplemem_memory_session_id: string | null
}

export interface LessonLivePromptsDebugSignal {
  enabled: boolean
}

export interface LessonVectorRetrievalDebugSignal {
  enabled: boolean
  hit_modes: LessonRetrievalMode[]
}

export interface LessonPromptMemoryDebugSignal {
  enabled: boolean
  injected_buckets: string[]
}

export interface LessonSemanticRecallDebugSignal {
  enabled: boolean
  recalled_memories: string[]
}

export interface LessonMemoryRuntimeDebugSignal {
  student_id: string
  project: string
  memory_session_id: string | null
  last_recall_status: 'success' | 'skipped' | 'degraded'
  last_recall_summary: string
  last_writeback_status: 'success' | 'skipped' | 'degraded'
  last_writeback_summary: string
  degradation_state:
    | 'healthy'
    | 'idle'
    | 'memory_disabled'
    | 'session_degraded'
    | 'recall_degraded'
    | 'writeback_degraded'
    | 'recall_and_writeback_degraded'
}

export interface LessonTeacherResponseAuditSignal {
  source:
    | 'policy'
    | 'policy_repaired'
    | 'llm'
    | 'llm_repaired'
    | 'fallback'
    | 'deterministic'
    | 'unknown'
  llm_called: boolean
  llm_provider: string
  latency_ms: number
  fallback_used: boolean
  fallback_reason: string
  repair_reason?: string
  route: string
}

export interface LessonTurnDebugSignals {
  live_prompts: LessonLivePromptsDebugSignal
  vector_retrieval: LessonVectorRetrievalDebugSignal
  prompt_memory: LessonPromptMemoryDebugSignal
  semantic_recall: LessonSemanticRecallDebugSignal
  memory_runtime: LessonMemoryRuntimeDebugSignal
  persona?: LessonPersonaDebugSignal
  response_audit?: LessonTeacherResponseAuditSignal
}

export interface LessonAiriPerformancePlan {
  emotion?: string
  expression?: string
  motion?: string
  speech_style?: 'normal' | 'slow_split' | 'short_prompt' | 'gentle_correction'
  mouth_intensity?: number
  interrupt_policy?: 'barge_in_allowed' | 'finish_current_sentence' | 'no_interrupt'
  content_source?: string
  fallback_allowed?: boolean
}

export interface LessonClassroomAffectState {
  student_confidence?: string
  teacher_energy?: string
  stuckness?: number
  interruption_state?: string
  recent_turn_labels?: string[]
}

export interface LessonPersonaDebugSignal {
  enabled?: boolean
  schema_version?: string
  profile_id?: string
  profile_version?: string
  display_name?: string
  voice_hint?: string
  allowed_to_shape?: string[]
  protected_authorities?: string[]
  relationship_student_id?: string
  relationship_signals?: string[]
  common_mistakes?: string[]
  preferences?: string[]
  mastery_signals?: string[]
  semantic_memories?: string[]
  affect_state?: LessonClassroomAffectState
  airi_performance?: LessonAiriPerformancePlan
}

export interface LessonTurnResult {
  page_uid: string
  block_uid: string | null
  turn_label: LessonTurnLabel
  teaching_action: LessonTeachingAction
  retrieval_mode: LessonRetrievalMode
  teacher_response: string
  state: LessonRuntimeState
  evaluation: LessonEvaluationResult | null
  retrieved_block_uids: string[]
  support_entry_uids: string[]
  return_anchor: string | null
  branch_reason: string | null
  debug_signals?: LessonTurnDebugSignals
}

export interface LessonAiriActionPayload {
  emotion: {
    name: string
    intensity: number
  }
  motion: string
  expression: string
  duration_ms: number
  teaching_action: LessonTeachingAction
  evaluation: LessonEvaluationResult | null
  reason: string
  turn_label: LessonTurnLabel
  speech_style?: 'normal' | 'slow_split' | 'short_prompt' | 'gentle_correction'
  mouth_intensity?: number
  interrupt_policy?: 'barge_in_allowed' | 'finish_current_sentence' | 'no_interrupt'
  content_source?: string
  fallback_allowed?: boolean
  performance_source?: string
}

export interface LessonTurnStreamRequest {
  url: string
  turnClientId: string
  learnerInput: string
  signal: AbortSignal
  payload: {
    page_uid: string
    student_id: string
    learner_input: string
    state: LessonRuntimeState
    turn_client_id: string
  }
}

export interface LessonTranscriptEntry {
  id: string
  speaker: 'teacher' | 'learner' | 'system'
  text: string
  created_at: number
  local_only?: boolean
  turn_label?: LessonTurnLabel
  teaching_action?: LessonTeachingAction
  retrieval_mode?: LessonRetrievalMode
  evaluation?: LessonEvaluationResult | null
}

export interface LessonPageOption {
  label: string
  value: string
  description: string
}

export interface LessonScopeOption {
  label: string
  value: string
}

export interface LessonCatalogPageRecord {
  page_uid: string
  page: number
  page_type: string
  page_intro_cn: string
}

export interface LessonCatalogScopeRecord {
  grade: string
  semester: string
  unit: string
  pages: LessonCatalogPageRecord[]
}

export interface LessonCatalogOutline {
  scope_count: number
  page_count: number
  block_count: number
  scopes: LessonCatalogScopeRecord[]
}

const lessonPilotManifestProjection = {
  grade: 'G5',
  semester: 'S1',
  unit: 'U3',
  pages: [24, 25, 26, 27, 28, 29, 30, 31],
  pageDescriptions: {
    24: '点餐与饮料句型',
    25: '菜单阅读与 salad',
    26: '早餐支线话题',
    27: '点餐对话复用',
    28: '食物描述与形容词',
    29: '阅读理解与偏好表达',
    30: '单元复习与复数练习',
    31: '故事阅读与农场话题',
  } satisfies Record<number, string>,
} as const

export const lessonPilotCatalogOutline: LessonCatalogOutline = {
  scope_count: 1,
  page_count: lessonPilotManifestProjection.pages.length,
  block_count: lessonPilotManifestProjection.pages.length,
  scopes: [{
    grade: lessonPilotManifestProjection.grade,
    semester: lessonPilotManifestProjection.semester,
    unit: lessonPilotManifestProjection.unit,
    pages: lessonPilotManifestProjection.pages.map(page => ({
      page_uid: `TB-${lessonPilotManifestProjection.grade}${lessonPilotManifestProjection.semester}${lessonPilotManifestProjection.unit}-P${page}`,
      page,
      page_type: 'pilot',
      page_intro_cn: lessonPilotManifestProjection.pageDescriptions[page],
    })),
  }],
}

export function buildLessonScopeLabel(scope: Pick<LessonCatalogScopeRecord, 'grade' | 'semester' | 'unit'>): string {
  return `${scope.grade} ${scope.semester} ${scope.unit}`
}

export function buildLessonPageOptionsFromCatalog(catalog: LessonCatalogOutline): LessonPageOption[] {
  return catalog.scopes.flatMap(scope =>
    scope.pages.map(page => ({
      label: `${buildLessonScopeLabel(scope)} · P${page.page}`,
      value: page.page_uid,
      description: `${page.page_type} · ${page.page_intro_cn}`,
    })),
  )
}

export function buildLessonPageOptionsFromScope(scope: LessonCatalogScopeRecord): LessonPageOption[] {
  return scope.pages.map(page => ({
    label: `P${page.page}`,
    value: page.page_uid,
    description: `${page.page_type} · ${page.page_intro_cn}`,
  }))
}

export function findLessonCatalogScopeByPageUid(
  catalog: LessonCatalogOutline,
  pageUid: string,
): LessonCatalogScopeRecord | null {
  const normalizedPageUid = pageUid.trim()
  if (!normalizedPageUid) {
    return null
  }

  return catalog.scopes.find(scope =>
    scope.pages.some(page => page.page_uid === normalizedPageUid),
  ) || null
}

export const lessonPilotPageOptions: LessonPageOption[] = buildLessonPageOptionsFromCatalog(lessonPilotCatalogOutline)

export const lessonActivityTypeLabels: Record<LessonActivityType, string> = {
  page_entry: '页面进入',
  teaching: '教学中',
  practice: '练习中',
  review: '复习中',
  branch: '支线展开',
}

export const lessonTurnLabelLabels: Record<LessonTurnLabel, string> = {
  page_entry: '开场',
  answer_question: '回答题目',
  ask_knowledge: '知识提问',
  ask_help: '求助',
  navigation: '导航',
  social: '闲聊回收',
}

export const lessonTeachingActionLabels: Record<LessonTeachingAction, string> = {
  page_intro: '页面导入',
  probe: '探测',
  confirm: '确认',
  hint: '提示',
  model: '示范',
  repeat_drill: '重复操练',
  explain: '解释',
  redirect: '回主线',
  complete: '完成',
}

export const lessonRetrievalModeLabels: Record<LessonRetrievalMode, string> = {
  none: '无检索',
  block: '当前块',
  page: '当前页',
  unit: '当前单元',
  branch: '支线',
}
