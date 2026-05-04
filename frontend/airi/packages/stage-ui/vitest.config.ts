import { join } from 'node:path'
import { cwd } from 'node:process'
import { fileURLToPath } from 'node:url'

import { loadEnv } from 'vite'
import { defineConfig } from 'vitest/config'

export default defineConfig(({ mode }) => {
  const workspaceRoot = fileURLToPath(new URL('../..', import.meta.url))

  return ({
    resolve: {
      alias: [
        { find: '~build/time', replacement: join(workspaceRoot, 'apps', 'stage-web', 'src', 'testing', 'lesson-browser-stubs', 'build-time.ts') },
        { find: '~build/git', replacement: join(workspaceRoot, 'apps', 'stage-web', 'src', 'testing', 'lesson-browser-stubs', 'build-git.ts') },
        { find: '~build/package', replacement: join(workspaceRoot, 'apps', 'stage-web', 'src', 'testing', 'lesson-browser-stubs', 'build-package.ts') },
      ],
      preserveSymlinks: true,
    },
    test: {
      include: ['src/**/*.test.ts'],
      env: loadEnv(mode, join(cwd(), 'packages', 'stage-ui'), ''),
    },
  })
})
