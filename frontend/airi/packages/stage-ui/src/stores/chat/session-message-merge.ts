import type { ChatHistoryItem } from '../../types/chat'

function extractMessageContent(message: ChatHistoryItem) {
  if (typeof message.content === 'string')
    return message.content

  if (Array.isArray(message.content)) {
    return message.content.map((part) => {
      if (typeof part === 'string')
        return part
      if (part && typeof part === 'object' && 'text' in part)
        return String(part.text ?? '')
      return ''
    }).join('')
  }

  return ''
}

function getMessageFingerprint(message: ChatHistoryItem) {
  return [
    message.id ?? '',
    message.role,
    message.createdAt ?? '',
    extractMessageContent(message),
  ].join('\u001F')
}

function getMessageIdentity(message: ChatHistoryItem) {
  if (message.id)
    return `id:${message.id}`

  return `fingerprint:${getMessageFingerprint(message)}`
}

export function mergeLoadedSessionMessages(storedMessages: ChatHistoryItem[], currentMessages: ChatHistoryItem[]) {
  if (currentMessages.length === 0)
    return storedMessages

  const currentMessagesToMerge = currentMessages.filter((message, index) => index !== 0 || message.role !== 'system')
  if (currentMessagesToMerge.length === 0)
    return storedMessages

  const mergedMessages = [...storedMessages]
  const seen = new Map(mergedMessages.map((message, index) => [getMessageIdentity(message), index]))

  for (const message of currentMessagesToMerge) {
    const identity = getMessageIdentity(message)
    const existingIndex = seen.get(identity)
    if (existingIndex !== undefined) {
      mergedMessages[existingIndex] = message
      continue
    }

    seen.set(identity, mergedMessages.length)
    mergedMessages.push(message)
  }

  const systemMessage = mergedMessages[0]?.role === 'system'
    ? mergedMessages[0]
    : currentMessages[0]?.role === 'system'
      ? currentMessages[0]
      : undefined

  if (mergedMessages.length === 0 && systemMessage)
    return [systemMessage]

  if (mergedMessages[0]?.role === 'system')
    return mergedMessages

  if (systemMessage)
    return [systemMessage, ...mergedMessages]

  return mergedMessages
}
