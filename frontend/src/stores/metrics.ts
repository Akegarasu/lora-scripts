import { defineStore } from 'pinia'

import { ApiError, apiClient, openJobMetricEvents } from '@/api/client'
import type {
  JobMetricBatch,
  JobMetricCursor,
  JobMetricPoint,
  JobMetricSeries,
  JobMetricsResponse,
} from '@/api/types'

const MAX_POINTS_PER_TAG = 20_000
const TERMINAL_STATES = new Set(['succeeded', 'failed', 'terminated', 'canceled', 'ended', 'missing'])

export type MetricStreamStatus =
  | 'idle'
  | 'loading'
  | 'connecting'
  | 'live'
  | 'disconnected'
  | 'ended'
  | 'unavailable'

let activeEvents: EventSource | null = null
let observationVersion = 0

function nowIso() {
  return new Date().toISOString()
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

function cursorPointCount(value: JobMetricCursor | undefined): number {
  if (value === undefined || value === '') return 0
  const parsed = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(parsed) && parsed >= 0 ? Math.floor(parsed) : 0
}

function normalizePoint(value: unknown): JobMetricPoint | null {
  if (!value || typeof value !== 'object') return null
  const point = value as Partial<JobMetricPoint>
  if (!isFiniteNumber(point.value) || !isFiniteNumber(point.step)) return null

  return {
    seq: isFiniteNumber(point.seq) ? point.seq : point.step,
    step: point.step,
    wallTime: isFiniteNumber(point.wallTime) ? point.wallTime : 0,
    value: point.value,
  }
}

function normalizeSeries(value: unknown): JobMetricSeries | null {
  if (!value || typeof value !== 'object') return null
  const series = value as Partial<JobMetricSeries>
  if (typeof series.tag !== 'string' || !series.tag.trim() || !Array.isArray(series.points)) return null
  return {
    tag: series.tag.trim(),
    points: series.points.map(normalizePoint).filter((point): point is JobMetricPoint => point !== null),
  }
}

function mergePoints(current: JobMetricPoint[], incoming: JobMetricPoint[]): JobMetricPoint[] {
  if (incoming.length === 0) return current

  const bySequence = new Map<number, JobMetricPoint>()
  for (const point of current) bySequence.set(point.seq, point)
  for (const point of incoming) bySequence.set(point.seq, point)

  const merged = [...bySequence.values()].sort((left, right) => {
    if (left.seq !== right.seq) return left.seq - right.seq
    if (left.step !== right.step) return left.step - right.step
    return left.wallTime - right.wallTime
  })
  return merged.length > MAX_POINTS_PER_TAG ? merged.slice(-MAX_POINTS_PER_TAG) : merged
}

function metricErrorMessage(error: unknown): { message: string; unavailable: boolean } {
  if (error instanceof ApiError && error.status === 404) {
    return {
      message: '任务记录不存在或已被清理。',
      unavailable: true,
    }
  }
  return {
    message: error instanceof Error ? error.message : String(error),
    unavailable: false,
  }
}

export const useMetricsStore = defineStore('metrics', {
  state: () => ({
    jobId: '',
    sourcePath: '',
    available: null as boolean | null,
    reportedPointCount: 0,
    parseErrors: [] as string[],
    cursor: undefined as JobMetricCursor | undefined,
    tags: [] as string[],
    pointsByTag: {} as Record<string, JobMetricPoint[]>,
    status: 'idle' as MetricStreamStatus,
    loading: false,
    loaded: false,
    terminal: false,
    error: '',
    lastEventAt: '',
  }),

  getters: {
    series(state): JobMetricSeries[] {
      return state.tags.map((tag) => ({ tag, points: state.pointsByTag[tag] || [] }))
    },
    pointCount(state): number {
      const retained = state.tags.reduce((total, tag) => total + (state.pointsByTag[tag]?.length || 0), 0)
      return Math.max(retained, state.reportedPointCount)
    },
    hasMetrics(state): boolean {
      return state.tags.some((tag) => (state.pointsByTag[tag]?.length || 0) > 0)
    },
  },

  actions: {
    reset(jobId = '') {
      this.jobId = jobId
      this.sourcePath = ''
      this.available = null
      this.reportedPointCount = 0
      this.parseErrors = []
      this.cursor = undefined
      this.tags = []
      this.pointsByTag = {}
      this.status = jobId ? 'loading' : 'idle'
      this.loading = !!jobId
      this.loaded = false
      this.terminal = false
      this.error = ''
      this.lastEventAt = ''
    },

    ingestSeries(seriesValues: unknown[]) {
      for (const value of seriesValues) {
        const series = normalizeSeries(value)
        if (!series) continue
        if (!this.tags.includes(series.tag)) this.tags.push(series.tag)
        this.pointsByTag[series.tag] = mergePoints(this.pointsByTag[series.tag] || [], series.points)
        if (series.points.length > 0) this.available = true
      }
      this.tags.sort((left, right) => left.localeCompare(right))
    },

    ingestBatch(value: unknown) {
      if (!value || typeof value !== 'object') return
      const batch = value as JobMetricBatch
      if (batch.cursor !== undefined) this.cursor = batch.cursor
      if (typeof batch.sourcePath === 'string' && batch.sourcePath) this.sourcePath = batch.sourcePath
      if (typeof batch.available === 'boolean') this.available = batch.available
      if (isFiniteNumber(batch.pointCount)) {
        this.reportedPointCount = Math.max(
          this.reportedPointCount,
          Math.max(0, batch.pointCount),
          cursorPointCount(batch.cursor),
        )
      } else {
        this.reportedPointCount = Math.max(this.reportedPointCount, cursorPointCount(batch.cursor))
      }
      if (Array.isArray(batch.errors)) {
        this.parseErrors = batch.errors.filter(
          (message): message is string => typeof message === 'string' && !!message.trim(),
        )
      }
      if (Array.isArray(batch.tags)) {
        for (const tag of batch.tags) {
          if (typeof tag === 'string' && tag.trim() && !this.tags.includes(tag.trim())) {
            this.tags.push(tag.trim())
          }
        }
      }
      if (Array.isArray(batch.events)) {
        for (const event of batch.events) this.ingestBatch(event)
      }
      if (Array.isArray(batch.series)) this.ingestSeries(batch.series)
      if (typeof batch.tag === 'string') {
        const points = [
          ...(Array.isArray(batch.points) ? batch.points : []),
          ...(batch.point ? [batch.point] : []),
        ]
        this.ingestSeries([{ tag: batch.tag, points }])
      }
      this.tags.sort((left, right) => left.localeCompare(right))
      this.lastEventAt = nowIso()
    },

    applySnapshot(snapshot: JobMetricsResponse, replace = false) {
      if (replace) {
        this.tags = []
        this.pointsByTag = {}
      }
      this.cursor = snapshot.cursor
      this.sourcePath = snapshot.sourcePath || this.sourcePath
      this.available = snapshot.available ?? true
      this.reportedPointCount = Math.max(
        replace ? 0 : this.reportedPointCount,
        Math.max(0, snapshot.pointCount ?? 0),
        cursorPointCount(snapshot.cursor),
      )
      this.parseErrors = Array.isArray(snapshot.errors)
        ? snapshot.errors.filter((message): message is string => typeof message === 'string' && !!message.trim())
        : []
      if (Array.isArray(snapshot.tags)) {
        for (const tag of snapshot.tags) {
          if (typeof tag === 'string' && tag.trim() && !this.tags.includes(tag.trim())) this.tags.push(tag.trim())
        }
      }
      this.ingestSeries(Array.isArray(snapshot.series) ? snapshot.series : [])
      this.tags.sort((left, right) => left.localeCompare(right))
      this.loaded = true
      this.loading = false
      this.lastEventAt = nowIso()
    },

    async observeJob(jobId: string, options: { terminal?: boolean } = {}) {
      const terminal = options.terminal ?? false
      if (!jobId) {
        observationVersion += 1
        this.disconnect('idle')
        this.reset()
        return
      }

      if (this.jobId === jobId && this.loaded) {
        if (terminal && !this.terminal) {
          this.terminal = true
          await this.refresh({ endAfter: true })
        }
        return
      }

      this.disconnect('idle')
      const version = ++observationVersion
      this.reset(jobId)
      this.terminal = terminal

      try {
        const snapshot = await apiClient.getJobMetrics(jobId, { maxPoints: 5000 })
        if (version !== observationVersion || this.jobId !== jobId) return
        this.applySnapshot(snapshot, true)
        this.error = ''
        if (terminal) {
          this.status = 'ended'
          return
        }
        this.connect(jobId)
      } catch (error) {
        if (version !== observationVersion || this.jobId !== jobId) return
        const detail = metricErrorMessage(error)
        this.loading = false
        this.loaded = true
        this.error = detail.message
        this.status = detail.unavailable ? 'unavailable' : 'disconnected'
      }
    },

    connect(jobId?: string) {
      const targetJobId = jobId || this.jobId
      if (!targetJobId || this.terminal) return
      if (activeEvents) activeEvents.close()
      this.status = 'connecting'

      activeEvents = openJobMetricEvents(targetJobId, this.cursor, {
        onOpen: () => {
          if (this.jobId !== targetJobId) return
          this.status = 'live'
          this.error = ''
          this.lastEventAt = nowIso()
        },
        onSnapshot: (snapshot) => {
          if (this.jobId !== targetJobId) return
          this.applySnapshot(snapshot)
          this.status = 'live'
          this.error = ''
        },
        onMetric: (batch) => {
          if (this.jobId !== targetJobId) return
          this.ingestBatch(batch)
          this.status = 'live'
          this.error = ''
        },
        onState: (state) => {
          if (this.jobId !== targetJobId) return
          if (state.cursor !== undefined) this.cursor = state.cursor
          this.lastEventAt = nowIso()
          if (state.state === 'missing') {
            this.terminal = true
            this.error = '任务记录不存在或已被清理。'
            this.disconnect('unavailable')
            return
          }
          if (state.state && TERMINAL_STATES.has(state.state)) {
            this.terminal = true
            this.disconnect('ended')
          }
        },
        onHeartbeat: () => {
          if (this.jobId === targetJobId) this.lastEventAt = nowIso()
        },
        onError: () => {
          if (this.jobId !== targetJobId || this.terminal) return
          // EventSource may reconnect by itself using Last-Event-ID. Keep the
          // instance alive while surfacing the degraded state to the user.
          this.status = 'disconnected'
          this.error = '实时指标连接已中断，图表保留最近收到的数据。'
        },
      })
    },

    async refresh(options: { endAfter?: boolean } = {}) {
      const jobId = this.jobId
      if (!jobId) return
      const version = observationVersion
      this.loading = !this.loaded
      try {
        const snapshot = await apiClient.getJobMetrics(jobId, {
          cursor: this.cursor,
          maxPoints: 5000,
        })
        if (version !== observationVersion || this.jobId !== jobId) return
        this.applySnapshot(snapshot)
        this.error = ''
        if (options.endAfter || this.terminal) {
          this.disconnect('ended')
        } else {
          this.connect(jobId)
        }
      } catch (error) {
        if (version !== observationVersion || this.jobId !== jobId) return
        const detail = metricErrorMessage(error)
        this.loading = false
        this.error = detail.message
        this.status = detail.unavailable ? 'unavailable' : 'disconnected'
      }
    },

    reconnect() {
      if (!this.jobId) return
      if (activeEvents) {
        activeEvents.close()
        activeEvents = null
      }
      this.status = 'connecting'
      this.error = ''
      void this.refresh()
    },

    disconnect(status: MetricStreamStatus = 'idle') {
      if (activeEvents) {
        activeEvents.close()
        activeEvents = null
      }
      this.status = status
    },
  },
})
