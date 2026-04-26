let playbackController: {
  stopAll?: (reason: string) => void
  stopByOwner?: (ownerId: string, reason: string) => void
} | undefined

const intent = {
  intentId: 'lesson-intent',
  streamId: 'lesson-stream',
  ownerId: 'peptutor-lesson',
  priority: 1,
  stream: new ReadableStream(),
  writeLiteral() {},
  writeSpecial() {},
  writeFlush() {},
  end() {},
  cancel() {},
}

const speechRuntimeStore = {
  registerPlaybackController(controller: typeof playbackController) {
    playbackController = controller
  },
  clearPlaybackController() {
    playbackController = undefined
  },
  stopByOwner(ownerId: string, reason: string = 'stop-by-owner') {
    playbackController?.stopByOwner?.(ownerId, reason)
  },
  stopAll(reason: string = 'stop-all') {
    playbackController?.stopAll?.(reason)
  },
  openIntent() {
    return intent
  },
}

export function useSpeechRuntimeStore() {
  return speechRuntimeStore
}
