import assert from 'node:assert/strict'
import { after, beforeEach, test } from 'node:test'
import { fileURLToPath } from 'node:url'
import { createPinia, setActivePinia } from 'pinia'
import { createServer } from 'vite'

const server = await createServer({
  root: fileURLToPath(new URL('..', import.meta.url)),
  server: { middlewareMode: true, watch: null, hmr: false },
})
const { useSettingsStore } = await server.ssrLoadModule('/src/stores/settings.ts')
const originalFetch = globalThis.fetch
const originalWindow = globalThis.window
const originalStorage = globalThis.localStorage

function state(overrides = {}) {
  return {
    enabled: true,
    running: true,
    transport: 'streamable-http',
    endpoint: 'http://127.0.0.1:28000/mcp/',
    error: null,
    ...overrides,
  }
}

function json(value, status = 200) {
  return new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
}

function deferred() {
  let resolve
  const promise = new Promise((done) => { resolve = done })
  return { promise, resolve }
}

beforeEach(() => {
  setActivePinia(createPinia())
  globalThis.window = { matchMedia: () => ({ matches: false }) }
  globalThis.localStorage = { getItem: () => null }
  globalThis.fetch = (url) => { throw new Error(`Unexpected request: ${url}`) }
})

after(async () => {
  await server.close()
  globalThis.fetch = originalFetch
  globalThis.window = originalWindow
  globalThis.localStorage = originalStorage
})

test('MCP preference is confirmed by the server and duplicate changes cannot race a pending update', async () => {
  const response = deferred()
  const requests = []
  globalThis.fetch = (url, init) => {
    requests.push({ url, init })
    return response.promise
  }
  const settings = useSettingsStore()
  settings.mcp = state()
  const saving = settings.setMcpEnabled(false)
  assert.equal(settings.savingMcp, true)
  assert.equal(settings.mcp.enabled, true, 'keep the confirmed preference while saving')
  await settings.setMcpEnabled(true)
  await settings.loadMcpSettings()
  assert.equal(requests.length, 1)
  assert.equal(requests[0].url, '/api/v2/settings/mcp')
  assert.equal(requests[0].init.method, 'PATCH')
  assert.deepEqual(JSON.parse(requests[0].init.body), { enabled: false })
  response.resolve(json(state({ enabled: false, running: false })))
  await saving
  assert.equal(settings.mcp.enabled, false)
  assert.equal(settings.savingMcp, false)
})

test('an uncertain MCP write reads back the accepted backend state instead of rolling back optimistically', async () => {
  const methods = []
  globalThis.fetch = async (_url, init) => {
    methods.push(init.method ?? 'GET')
    if (init.method === 'PATCH') throw new Error('connection lost after write')
    return json(state({ enabled: false, running: false }))
  }
  const settings = useSettingsStore()
  settings.mcp = state()
  await settings.setMcpEnabled(false)
  assert.deepEqual(methods, ['PATCH', 'GET'])
  assert.equal(settings.mcp.enabled, false)
  assert.match(settings.mcpError, /connection lost/)
  assert.equal(settings.savingMcp, false)
})

test('failed MCP write and readback leave status unknown and prevent another blind update', async () => {
  let calls = 0
  globalThis.fetch = async () => {
    calls += 1
    return json({ detail: 'service unavailable' }, 503)
  }
  const settings = useSettingsStore()
  settings.mcp = state()
  await settings.setMcpEnabled(false)
  assert.equal(settings.mcp, null)
  assert.equal(settings.savingMcp, false)
  assert.match(settings.mcpError, /service unavailable/)
  await settings.setMcpEnabled(false)
  assert.equal(calls, 2)
})

test('a loaded MCP preference can be enabled while the service reports a startup failure', async () => {
  globalThis.fetch = async () => json(state({ running: false, error: 'MCP dependency missing' }))
  const settings = useSettingsStore()
  await settings.loadMcpSettings()
  assert.equal(settings.mcp.enabled, true)
  assert.equal(settings.mcp.running, false)
  assert.equal(settings.mcp.error, 'MCP dependency missing')
  assert.equal(settings.mcpError, '')
  assert.equal(settings.loadingMcp, false)
})

test('refresh failure discards stale MCP state, and a later successful refresh restores control', async () => {
  const settings = useSettingsStore()
  settings.mcp = state()
  globalThis.fetch = async () => json({ detail: 'offline' }, 503)
  await settings.loadMcpSettings()
  assert.equal(settings.mcp, null)
  assert.match(settings.mcpError, /offline/)
  assert.equal(settings.loadingMcp, false)
  globalThis.fetch = async () => json(state({ enabled: false, running: false }))
  await settings.loadMcpSettings()
  assert.equal(settings.mcp.enabled, false)
  assert.equal(settings.mcpError, '')
})
