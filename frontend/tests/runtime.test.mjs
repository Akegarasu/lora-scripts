import assert from 'node:assert/strict'
import { after, beforeEach, test } from 'node:test'
import { fileURLToPath } from 'node:url'
import { createPinia, setActivePinia } from 'pinia'
import { createServer } from 'vite'
import { createRenderer, nextTick, reactive, ssrContextKey } from 'vue'

const server = await createServer({
  root: fileURLToPath(new URL('..', import.meta.url)),
  server: { middlewareMode: true, watch: null },
})
const { useJobsStore } = await server.ssrLoadModule('/src/stores/jobs.ts')
const { useCaptionStore } = await server.ssrLoadModule('/src/stores/caption.ts')
const { alternateNotation, modelNumberText, toScientificNotation, validateNumericInput } =
  await server.ssrLoadModule('/src/utils/scientificNumber.ts')
const { default: JobConsole } = await server.ssrLoadModule('/src/components/JobConsole.vue')
const originalFetch = globalThis.fetch
const originalWindow = globalThis.window
const originalEventSource = globalThis.EventSource
const streams = []
const pendingTimers = new Map()
let nextTimerId = 0

class FakeEventSource {
  constructor(url) {
    this.url = url
    this.closed = false
    streams.push(this)
  }
  addEventListener() {}
  close() { this.closed = true }
}

function deferred() {
  let resolve
  const promise = new Promise((done) => { resolve = done })
  return { promise, resolve }
}

function json(value) {
  return new Response(JSON.stringify(value), { headers: { 'Content-Type': 'application/json' } })
}

function job(id = 'job-a') {
  return { id, state: 'running', revision: 1, modelId: 'model' }
}

async function flush() {
  await new Promise((resolve) => setImmediate(resolve))
}

beforeEach(() => {
  setActivePinia(createPinia())
  streams.length = 0
  pendingTimers.clear()
  globalThis.EventSource = FakeEventSource
  globalThis.window = {
    setTimeout(callback) {
      const id = ++nextTimerId
      pendingTimers.set(id, callback)
      return id
    },
    clearTimeout(id) { pendingTimers.delete(id) },
  }
  globalThis.fetch = (url) => { throw new Error(`Unexpected request: ${url}`) }
})

after(async () => {
  await server.close()
  globalThis.fetch = originalFetch
  globalThis.window = originalWindow
  globalThis.EventSource = originalEventSource
})

test('disconnect cancels an in-flight training job selection', async () => {
  const response = deferred()
  globalThis.fetch = () => response.promise
  const jobs = useJobsStore()
  const selection = jobs.selectJob('job-a')
  jobs.disconnect()
  response.resolve(json(job()))
  await selection
  assert.equal(streams.length, 0)
  assert.equal(jobs.selectedJob, null)
})

test('a list response arriving after disconnect cannot start observation', async () => {
  const response = deferred()
  globalThis.fetch = () => response.promise
  const jobs = useJobsStore()
  const loading = jobs.loadJobs()
  jobs.disconnect()
  response.resolve(json({ jobs: [job()] }))
  await loading
  assert.equal(jobs.selectedJobId, '')
  assert.equal(streams.length, 0)
})

test('reconnection ignores an older static log response for the same job', async () => {
  const response = deferred()
  globalThis.fetch = (url) => url.includes('/logs') ? response.promise : Promise.resolve(json(job()))
  const jobs = useJobsStore()
  jobs.selectedJobId = 'job-a'
  const loading = jobs.loadStaticLogs('job-a')
  await jobs.reconnectSelectedJob()
  jobs.logLines = ['new stream']
  response.resolve(json({ lines: ['old snapshot'] }))
  await loading
  assert.deepEqual([...jobs.logLines], ['new stream'])
  assert.equal(streams.length, 1)
  jobs.disconnect()
})

test('stopping caption observation cancels an in-flight selection', async () => {
  const response = deferred()
  globalThis.fetch = (url) => {
    if (url.includes('/items?')) return Promise.resolve(json({ items: [], total: 0, offset: 0 }))
    if (url.includes('/logs?')) return Promise.resolve(json({ lines: [], cursor: 0 }))
    return response.promise
  }
  const caption = useCaptionStore()
  const selection = caption.selectJob('job-a')
  caption.stopObservation()
  response.resolve(json(job()))
  await selection
  assert.equal(streams.length, 0)
  assert.equal(caption.currentJob, null)
  assert.equal(caption.currentLoading, false)
})

test('caption polling waits for each response and stops while a request is pending', async () => {
  const response = deferred()
  let requestCount = 0
  globalThis.fetch = () => {
    requestCount += 1
    return response.promise
  }
  const caption = useCaptionStore()
  caption.currentJobId = 'job-a'
  caption.startPolling('job-a')
  assert.equal(requestCount, 1)
  assert.equal(pendingTimers.size, 0)
  caption.stopObservation()
  response.resolve(json(job()))
  await flush()
  assert.equal(caption.currentJob, null)
  assert.equal(caption.streamStatus, 'idle')
  assert.equal(pendingTimers.size, 0)
})

test('committing a previous caption job cannot reopen its stream after navigation', async () => {
  const response = deferred()
  globalThis.fetch = () => response.promise
  const caption = useCaptionStore()
  caption.currentJobId = 'job-a'
  const commit = caption.commitCurrentJob({})
  caption.stopObservation()
  caption.currentJobId = 'job-b'
  response.resolve(json(job()))
  await commit
  assert.equal(streams.length, 0)
  assert.equal(caption.currentJobId, 'job-b')
})

test('zero with a huge exponent converts without expanding a huge string', () => {
  for (const input of ['0e99999999999', '0e-99999999999', '-0.000e99999999999']) {
    const result = validateNumericInput(input)
    assert.equal(result.status, 'valid')
    assert.equal(Math.abs(result.value), 0)
    assert.deepEqual(alternateNotation(input, result.value), { label: '小数', value: '0' })
    assert.equal(toScientificNotation(input), '0e0')
  }
  assert.equal(modelNumberText(-0), '-0')
  assert.deepEqual(alternateNotation('1.25e-4', 0.000125), { label: '小数', value: '0.000125' })
  assert.equal(toScientificNotation('-0.000125'), '-1.25e-4')
})

test('the console follows a rolling log buffer even when its length stays fixed', async () => {
  // A Vue host renderer exercises watchers without adding a browser or DOM dependency.
  const renderer = createRenderer({
    createComment: (text) => ({ text }),
    insert() {},
    remove() {},
    parentNode: () => null,
    nextSibling: () => null,
  })
  const lines = reactive(['first', 'second'])
  const app = renderer.createApp({ ...JobConsole, render: () => null }, { lines })
  app.provide(ssrContextKey, {})
  const instance = app.mount({})
  const viewport = { scrollTop: 0, scrollHeight: 100 }
  instance.$.setupState.viewport = viewport
  try {
    await nextTick()
    assert.equal(viewport.scrollTop, 100)
    viewport.scrollHeight = 200
    lines.push('third')
    lines.splice(0, 1)
    await nextTick()
    await nextTick()
    assert.equal(lines.length, 2)
    assert.equal(viewport.scrollTop, 200)
  } finally {
    app.unmount()
  }
})
