import type { BeatSyncController } from './beat-sync'
import type { MotionManagerPluginContext } from './motion-manager'

import { describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

import { normalizeLive2DMotionDeltaSeconds, useMotionUpdatePluginBeatSync } from './motion-manager'

function createBeatSyncControllerFixture(targets = { x: 1, y: 2, z: 3 }): BeatSyncController {
  return {
    targetX: ref(targets.x),
    targetY: ref(targets.y),
    targetZ: ref(targets.z),
    velocityX: ref(0),
    velocityY: ref(0),
    velocityZ: ref(0),
    updateTargets: vi.fn(),
    scheduleBeat: vi.fn(),
    debugState: () => ({
      primed: true,
      patternStarted: true,
      lastBeatTimestamp: 0,
      lastInterval: 600,
      avgInterval: 600,
      bpm: 100,
      style: 'sway-sine',
      segments: [],
    }),
    setStyle: vi.fn(),
    getStyle: () => 'sway-sine',
    setAutoStyleShift: vi.fn(),
  }
}

function createCoreModelFixture() {
  const parameters = new Map<string, number>([
    ['ParamAngleX', 0],
    ['ParamAngleY', 0],
    ['ParamAngleZ', 0],
  ])

  return {
    getParameterValueById: (id: string) => parameters.get(id) ?? 0,
    setParameterValueById: (id: string, value: number) => {
      parameters.set(id, value)
    },
    parameters,
  }
}

function createPluginContext(timeDelta: number, model = createCoreModelFixture()): MotionManagerPluginContext {
  return {
    model: model as any,
    now: 1000,
    timeDelta,
    internalModel: {} as any,
    motionManager: {} as any,
    modelParameters: ref({}),
    live2dIdleAnimationEnabled: ref(true),
    live2dAutoBlinkEnabled: ref(true),
    live2dForceAutoBlinkEnabled: ref(false),
    isIdleMotion: true,
    handled: false,
    markHandled: vi.fn(),
  }
}

describe('live2d motion manager', () => {
  it('normalizes browser timestamp deltas to bounded seconds', () => {
    expect(normalizeLive2DMotionDeltaSeconds(16)).toBeCloseTo(0.016)
    expect(normalizeLive2DMotionDeltaSeconds(0.016)).toBeCloseTo(0.016)
    expect(normalizeLive2DMotionDeltaSeconds(250)).toBeCloseTo(0.1)
    expect(normalizeLive2DMotionDeltaSeconds(Number.NaN)).toBe(0)
  })

  it('keeps beat-sync physics finite when requestAnimationFrame passes milliseconds', () => {
    const beatSync = createBeatSyncControllerFixture()
    const model = createCoreModelFixture()
    const plugin = useMotionUpdatePluginBeatSync(beatSync)

    plugin(createPluginContext(16, model))

    expect(model.parameters.get('ParamAngleX')).toBeGreaterThan(0)
    expect(model.parameters.get('ParamAngleX')).toBeLessThan(0.1)
    expect(model.parameters.get('ParamAngleY')).toBeLessThan(0.2)
    expect(model.parameters.get('ParamAngleZ')).toBeLessThan(0.3)
  })
})
