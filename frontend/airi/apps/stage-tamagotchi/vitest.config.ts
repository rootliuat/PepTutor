import { join, resolve } from 'node:path'

import { defineConfig } from 'vitest/config'

const repoRoot = resolve(import.meta.dirname, '..', '..')

export default defineConfig({
  resolve: {
    alias: [
      { find: '@proj-airi/electron-eventa/electron-updater', replacement: resolve(join(repoRoot, 'packages', 'electron-eventa', 'src', 'electron-updater', 'index.ts')) },
      { find: '@proj-airi/electron-eventa', replacement: resolve(join(repoRoot, 'packages', 'electron-eventa', 'src', 'index.ts')) },
      { find: '@proj-airi/electron-vueuse/main', replacement: resolve(join(repoRoot, 'packages', 'electron-vueuse', 'src', 'main', 'index.ts')) },
      { find: '@proj-airi/electron-vueuse', replacement: resolve(join(repoRoot, 'packages', 'electron-vueuse', 'src', 'index.ts')) },
      { find: '@proj-airi/plugin-sdk/plugin-host', replacement: resolve(join(repoRoot, 'packages', 'plugin-sdk', 'src', 'plugin-host', 'index.ts')) },
      { find: '@proj-airi/plugin-sdk', replacement: resolve(join(repoRoot, 'packages', 'plugin-sdk', 'src', 'index.ts')) },
    ],
  },
  test: {
    include: ['src/**/*.test.ts'],
    exclude: ['**/node_modules/**', '**/.git/**'],
  },
})
