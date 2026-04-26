export async function waitForOptionalInitialization(
  task: Promise<unknown>,
  options: {
    timeoutMs: number
    label: string
    onError?: (error: unknown) => void
  },
) {
  let timeoutHandle: ReturnType<typeof setTimeout> | undefined

  try {
    const result = await Promise.race([
      task.then(() => 'resolved' as const).catch((error) => {
        options.onError?.(error)
        return 'rejected' as const
      }),
      new Promise<'timed-out'>((resolve) => {
        timeoutHandle = setTimeout(() => resolve('timed-out'), options.timeoutMs)
      }),
    ])

    if (result === 'timed-out') {
      console.warn(`[runtime-bootstrap] ${options.label} did not finish within ${options.timeoutMs}ms; continuing startup.`)
    }
  }
  finally {
    if (timeoutHandle)
      clearTimeout(timeoutHandle)
  }
}
