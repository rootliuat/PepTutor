import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    name: 'stage-ui-live2d',
    include: ['src/**/*.test.ts'],
  },
})
