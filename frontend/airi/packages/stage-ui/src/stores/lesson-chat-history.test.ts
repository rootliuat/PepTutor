import { describe, expect, it } from 'vitest'

import {
  isLessonActiveTabLeaseAvailable,
  lessonActiveTabLeaseStorageKeyForIdentity,
  lessonActiveTabLeaseTtlMs,
  lessonChatHistoryMetaFromSummary,
  lessonChatHistoryRecordFromPayload,
  lessonChatHistorySafetyFromSummary,
  lessonRuntimeSnapshotFromHistoryPayload,
  lessonRuntimeSnapshotMatchesIdentity,
  parseLessonActiveTabLease,
} from './lesson-chat-history'

describe('lesson chat history files', () => {
  it('restores v3 raw chat messages as the chat UI source', () => {
    const record = lessonChatHistoryRecordFromPayload({
      format: 'peptutor-chat-history:v3',
      metadata: {
        session_id: 'lesson-session-1',
        user_id: 'local',
        character_id: 'peptutor-mili-teacher',
        title: 'P4',
        created_at: 1766720000000,
        updated_at: 1766720001000,
      },
      raw_chat_session: {
        messages: [
          {
            role: 'system',
            content: 'private system prompt',
          },
          {
            role: 'assistant',
            content: '你好，我是米粒老师。',
            slices: [{ type: 'text', text: '你好，我是米粒老师。' }],
            tool_results: [],
            createdAt: 1766720000001,
            id: 'assistant-1',
          },
          {
            role: 'user',
            content: 'Let\'s try',
            createdAt: 1766720000002,
            id: 'user-1',
          },
        ],
      },
      dialogue: [
        {
          role: 'assistant',
          speaker: '米粒',
          text: 'dialogue fallback should not replace raw',
        },
      ],
    })

    expect(record?.messages).toHaveLength(2)
    expect(record?.messages[0]).toMatchObject({
      role: 'assistant',
      content: '你好，我是米粒老师。',
      id: 'assistant-1',
    })
    expect(record?.messages[1]).toMatchObject({
      role: 'user',
      content: 'Let\'s try',
      id: 'user-1',
    })
    expect(JSON.stringify(record?.messages)).not.toContain('private system prompt')
    expect(JSON.stringify(record?.messages)).not.toContain('dialogue fallback should not replace raw')
  })

  it('keeps v2 dialogue readable as a legacy fallback', () => {
    const record = lessonChatHistoryRecordFromPayload({
      format: 'peptutor-chat-history:v2',
      metadata: {
        session_id: 'legacy-session',
        user_id: 'local',
        character_id: 'peptutor-mili-teacher',
        created_at: 1766720000000,
        updated_at: 1766720001000,
      },
      dialogue: [
        {
          speaker: '米粒',
          text: '我们先看这一页。',
        },
        {
          speaker: '学生',
          text: '我想学第二块。',
        },
      ],
    })

    expect(record?.messages.map(message => message.role)).toEqual(['assistant', 'user'])
    expect(record?.messages.map(message => message.content)).toEqual(['我们先看这一页。', '我想学第二块。'])
  })

  it('restores runtime snapshot separately from chat messages', () => {
    const snapshot = lessonRuntimeSnapshotFromHistoryPayload({
      format: 'peptutor-chat-history:v3',
      metadata: {
        session_id: 'lesson-session-1',
      },
      restore_snapshot: {
        version: 1,
        selectedPageUid: 'TB-G5S1U1-P4',
        studentId: 'demo-student',
        runtimeState: {
          current_page_uid: 'TB-G5S1U1-P4',
          current_block_uid: 'TB-G5S1U1-P4-D2',
        },
        updatedAt: 1766720001000,
      },
    })

    expect(snapshot?.selectedPageUid).toBe('TB-G5S1U1-P4')
    expect(snapshot?.runtimeState).toMatchObject({
      current_block_uid: 'TB-G5S1U1-P4-D2',
    })
  })

  it('uses explicit metadata student id when restoring page-only histories', () => {
    const snapshot = lessonRuntimeSnapshotFromHistoryPayload({
      format: 'peptutor-chat-history:v3',
      metadata: {
        session_id: 'page-only-session',
        user_id: 'local',
        student_id: 'student-a',
        page_uid: 'TB-G5S1U3-P24',
        updated_at: 1766720001000,
      },
    })

    expect(snapshot).toMatchObject({
      selectedPageUid: 'TB-G5S1U3-P24',
      studentId: 'student-a',
      runtimeState: null,
    })
  })

  it('falls back to metadata student id when a v1 snapshot omits it', () => {
    const snapshot = lessonRuntimeSnapshotFromHistoryPayload({
      format: 'peptutor-chat-history:v3',
      metadata: {
        session_id: 'snapshot-without-student',
        user_id: 'local',
        student_id: 'student-a',
      },
      restore_snapshot: {
        version: 1,
        selectedPageUid: 'TB-G5S1U3-P24',
        runtimeState: {
          current_page_uid: 'TB-G5S1U3-P24',
          current_block_uid: 'TB-G5S1U3-P24-D1',
        },
        updatedAt: 1766720001000,
      },
    })

    expect(snapshot?.studentId).toBe('student-a')
  })

  it('matches restorable lesson snapshots by page and student identity', () => {
    const snapshot = lessonRuntimeSnapshotFromHistoryPayload({
      format: 'peptutor-chat-history:v3',
      metadata: {
        session_id: 'lesson-session-1',
      },
      restore_snapshot: {
        version: 1,
        selectedPageUid: 'TB-G5S1U3-P24',
        studentId: 'student-a',
        runtimeState: {
          student_id: 'student-a',
          current_page_uid: 'TB-G5S1U3-P24',
          current_block_uid: 'TB-G5S1U3-P24-D2',
        },
        updatedAt: 1766720001000,
      },
    })

    expect(lessonRuntimeSnapshotMatchesIdentity(snapshot, {
      pageUid: 'TB-G5S1U3-P24',
      studentId: 'student-a',
    })).toBe(true)
    expect(lessonRuntimeSnapshotMatchesIdentity(snapshot, {
      pageUid: 'TB-G5S1U3-P25',
      studentId: 'student-a',
    })).toBe(false)
    expect(lessonRuntimeSnapshotMatchesIdentity(snapshot, {
      pageUid: 'TB-G5S1U3-P24',
      studentId: 'student-b',
    })).toBe(false)
    expect(lessonRuntimeSnapshotMatchesIdentity(null, {
      pageUid: 'TB-G5S1U3-P24',
      studentId: 'student-a',
    })).toBe(false)
  })

  it('marks v3 clean block histories as restorable', () => {
    const safety = lessonChatHistorySafetyFromSummary({
      session_id: 'restorable-session',
      history_format: 'peptutor-chat-history:v3',
      audit_status: 'clean',
      restore_safety: 'block',
      message_page_ownership: 'missing',
      history_access: 'continue',
    })

    expect(safety).toMatchObject({
      sessionId: 'restorable-session',
      access: 'continue',
      label: '可继续',
      canRestore: true,
    })
  })

  it('uses the backend-scoped student id as the remote session user id', () => {
    const meta = lessonChatHistoryMetaFromSummary({
      session_id: 'student-a-session',
      user_id: 'student-a',
      student_id: 'student-a',
      character_id: 'peptutor-mili-teacher',
      title: 'P24',
      created_at: 1766720000000,
      updated_at: 1766720001000,
      page_uid: 'TB-G5S1U3-P24',
    })

    expect(meta).toMatchObject({
      sessionId: 'student-a-session',
      userId: 'student-a',
      characterId: 'peptutor-mili-teacher',
      title: 'P24',
    })
  })

  it('keeps unverified and legacy histories view-only', () => {
    const unverified = lessonChatHistorySafetyFromSummary({
      session_id: 'unverified-session',
      history_format: 'peptutor-chat-history:v3',
      audit_status: 'clean',
      restore_safety: 'page',
      message_page_ownership: 'missing',
      history_access: 'view_only',
      audit_reason: 'single explicit page identity found; message ownership is unverified',
    })
    const legacy = lessonChatHistorySafetyFromSummary({
      session_id: 'legacy-session',
      history_format: 'peptutor-chat-history:v2',
      audit_status: 'legacy_readonly',
      restore_safety: 'none',
      message_page_ownership: 'missing',
      history_access: 'read_only',
    })

    expect(unverified).toMatchObject({
      access: 'view_only',
      label: '不可恢复',
      detail: '可查看聊天，但不能恢复课堂状态',
      canRestore: false,
    })
    expect(legacy).toMatchObject({
      access: 'read_only',
      label: '只读',
      canRestore: false,
    })
  })

  it('treats active lesson tab leases as single-writer ownership', () => {
    expect(parseLessonActiveTabLease('not-json')).toBeNull()
    expect(parseLessonActiveTabLease(JSON.stringify({
      tabId: 'tab-a',
      updatedAt: 1000,
    }))).toEqual({
      tabId: 'tab-a',
      updatedAt: 1000,
    })

    expect(isLessonActiveTabLeaseAvailable(null, 'tab-a', 2000)).toBe(true)
    expect(isLessonActiveTabLeaseAvailable({
      tabId: 'tab-a',
      updatedAt: 1000,
    }, 'tab-a', 2000)).toBe(true)
    expect(isLessonActiveTabLeaseAvailable({
      tabId: 'tab-b',
      updatedAt: 1000,
    }, 'tab-a', 2000)).toBe(false)
    expect(isLessonActiveTabLeaseAvailable({
      tabId: 'tab-b',
      updatedAt: 1000,
    }, 'tab-a', 1000 + lessonActiveTabLeaseTtlMs + 1)).toBe(true)
  })

  it('scopes active lesson tab leases by student and page', () => {
    const firstStudent = lessonActiveTabLeaseStorageKeyForIdentity({
      pageUid: 'TB-G5S1U3-P24',
      studentId: 'student-a',
    })
    const secondStudent = lessonActiveTabLeaseStorageKeyForIdentity({
      pageUid: 'TB-G5S1U3-P24',
      studentId: 'student-b',
    })
    const secondPage = lessonActiveTabLeaseStorageKeyForIdentity({
      pageUid: 'TB-G5S1U3-P25',
      studentId: 'student-a',
    })

    expect(firstStudent).toContain('peptutor/lesson/active-tab-lease/v2/')
    expect(firstStudent).not.toBe(secondStudent)
    expect(firstStudent).not.toBe(secondPage)
  })
})
