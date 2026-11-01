import assert from 'node:assert/strict'
import { after, beforeEach, test } from 'node:test'
import { fileURLToPath } from 'node:url'
import { createPinia, setActivePinia } from 'pinia'
import { createServer } from 'vite'

const server = await createServer({
  root: fileURLToPath(new URL('..', import.meta.url)),
  server: { middlewareMode: true, watch: null, hmr: false },
})
const { useDraftStore } = await server.ssrLoadModule('/src/stores/draft.ts')
const originalStorage = globalThis.localStorage
const saved = new Map()
const skipLayers = {
  name: 'sample_uncond_skip_layers', type: 'string', group: 'sampling',
  default: '22', extra: { preserveEmpty: true },
}

beforeEach(() => {
  setActivePinia(createPinia())
  saved.clear()
  globalThis.localStorage = {
    getItem: (key) => saved.get(key) ?? null,
    setItem: (key, value) => saved.set(key, value),
  }
})

after(async () => {
  await server.close()
  globalThis.localStorage = originalStorage
})

test('MOSS empty skip layers remains an explicit override through save and catalog reload', () => {
  const draft = useDraftStore()
  draft.resetForTrainer([skipLayers], 'moss_image.lora', 'before', false)
  draft.setValue(skipLayers, '')
  assert.equal(draft.buildDraft('moss_image.lora').params.sample_uncond_skip_layers, '')
  assert.equal(draft.persistForTrainer('moss_image.lora', [skipLayers]), true)
  draft.resetForTrainer([skipLayers], 'moss_image.lora', 'after', true)
  assert.equal(draft.getValue(skipLayers), '')
  draft.resetValue(skipLayers)
  assert.equal(draft.getValue(skipLayers), undefined)
})

test('ordinary empty values still remove an override', () => {
  const draft = useDraftStore()
  const ordinary = { name: 'notes', type: 'string', group: 'advanced' }
  draft.resetForTrainer([ordinary], 'sd.lora', 'hash', false)
  draft.setValue(ordinary, 'value')
  draft.setValue(ordinary, '')
  assert.equal(draft.getValue(ordinary), undefined)
})

test('MOSS preview starts with upstream CFG and preserves saved user choices', () => {
  const draft = useDraftStore()
  draft.resetForTrainer([skipLayers], 'moss_image.lora', 'hash', false)
  assert.equal(draft.sample.prompts[0].cfgScale, 3)
  assert.equal(draft.sample.prompts[0].steps, 50)
  draft.sample.prompts[0].cfgScale = 1
  draft.sample.prompts[0].steps = 10
  draft.persistForTrainer('moss_image.lora', [skipLayers])
  draft.resetForTrainer([skipLayers], 'moss_image.lora', 'new-hash', true)
  assert.equal(draft.sample.prompts[0].cfgScale, 1)
  assert.equal(draft.sample.prompts[0].steps, 10)
  draft.resetForTrainer([skipLayers], 'flux.lora', 'hash', false)
  assert.equal(draft.sample.prompts[0].steps, 20)
  assert.equal(draft.sample.prompts[0].cfgScale, 1)
})
