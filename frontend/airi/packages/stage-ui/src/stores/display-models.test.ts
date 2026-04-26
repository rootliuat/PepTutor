import { readFileSync } from 'node:fs'

import { describe, expect, it } from 'vitest'

const displayModelsSource = readFileSync(new URL('./display-models.ts', import.meta.url), 'utf8')

describe('display models store source', () => {
  it('keeps bundled Live2D preset urls for non-web runtimes and rewrites stage-web to preset routes', () => {
    expect(displayModelsSource).toContain(`new URL('../assets/live2d/models/hiyori_pro_zh.zip', import.meta.url).href`)
    expect(displayModelsSource).toContain(`new URL('../assets/live2d/models/hiyori_free_zh.zip', import.meta.url).href`)
    expect(displayModelsSource).toContain(`resolvePresetLive2dUrl(presetLive2dProAssetUrl, '/__airi/live2d/preset/hiyori_pro_zh')`)
    expect(displayModelsSource).toContain(`resolvePresetLive2dUrl(presetLive2dFreeAssetUrl, '/__airi/live2d/preset/hiyori_free_zh')`)
  })
})
