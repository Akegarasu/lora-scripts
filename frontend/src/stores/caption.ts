import { defineStore } from 'pinia'

import { apiClient, openCaptionJobEvents } from '@/api/client'
import type {
  CaptionCommitRequest,
  CaptionDatasetInspectRequest,
  CaptionDatasetItem,
  CaptionDatasetSummary,
  CaptionItemState,
  CaptionJobCreateRequest,
  CaptionJobItem,
  CaptionJobState,
  CaptionJobSummary,
  CaptionModelSummary,
} from '@/api/types'

const TERMINAL_STATES = new Set<CaptionJobState>([
  'awaiting_review',
  'succeeded',
  'partial',
  'failed',
  'canceled',
  'interrupted',
])
const POLL_INTERVAL = 1800
const RESULT_REFRESH_INTERVAL = 1500

export type CaptionStreamStatus = 'idle' | 'connecting' | 'live' | 'polling' | 'ended' | 'error'

let activeEvents: EventSource | null = null
let pollTimer: number | undefined
let observationVersion = 0
let refreshedItemsRevision = -1
let lastLogFetchAt = 0
let datasetItemsRequestVersion = 0
let currentItemsRequestVersion = 0
let datasetItemsLoadingVersion = 0
let currentItemsLoadingVersion = 0
let datasetInspectVersion = 0
let resultRefreshTimer: number | undefined
let lastResultRefreshAt = 0

function isTerminal(state?: CaptionJobState) {
  return !!state && TERMINAL_STATES.has(state)
}

function message(error: unknown) {
  return error instanceof Error ? error.message : String(error)
}

function nowIso() {
  return new Date().toISOString()
}

export const useCaptionStore = defineStore('caption', {
  state: () => ({
    models: [] as CaptionModelSummary[],
    defaultModelId: '',
    modelsLoading: false,
    modelsError: '',

    dataset: null as CaptionDatasetSummary | null,
    datasetItems: [] as CaptionDatasetItem[],
    datasetItemsTotal: 0,
    datasetOffset: 0,
    datasetLimit: 100,
    datasetQuery: '',
    datasetCaptionState: 'all',
    datasetLoading: false,
    datasetError: '',
    savingDatasetItemId: '',

    jobs: [] as CaptionJobSummary[],
    jobsLoading: false,
    jobsError: '',
    currentJobId: '',
    currentJob: null as CaptionJobSummary | null,
    currentItems: [] as CaptionJobItem[],
    currentItemsTotal: 0,
    currentItemsOffset: 0,
    currentItemsLimit: 24,
    currentItemsQuery: '',
    currentItemsState: '' as '' | CaptionItemState,
    currentLogs: [] as string[],
    currentLogsCursor: 0,
    logsLoading: false,
    logsError: '',
    currentLoading: false,
    currentError: '',
    starting: false,
    committing: false,
    canceling: false,
    editingItemId: '',
    streamStatus: 'idle' as CaptionStreamStatus,
    streamError: '',
    lastEventAt: '',
  }),

  getters: {
    selectedModel(state): CaptionModelSummary | null {
      return state.models.find((model) => model.id === state.defaultModelId) || null
    },
    currentIsTerminal(state): boolean {
      return isTerminal(state.currentJob?.state)
    },
  },

  actions: {
    async loadModels(options: { silent?: boolean } = {}) {
      if (!options.silent) this.modelsLoading = true
      this.modelsError = ''
      try {
        const response = await apiClient.listCaptionModels()
        this.models = response.models
        this.defaultModelId = response.defaultModelId
      } catch (error) {
        this.modelsError = message(error)
      } finally {
        this.modelsLoading = false
      }
    },

    async inspectDataset(request: CaptionDatasetInspectRequest) {
      const inspectVersion = ++datasetInspectVersion
      this.datasetLoading = true
      this.datasetError = ''
      try {
        const response = await apiClient.inspectCaptionDataset(request)
        if (inspectVersion !== datasetInspectVersion) return null
        datasetItemsRequestVersion += 1
        this.dataset = response.dataset
        this.datasetItems = response.items.slice(0, this.datasetLimit)
        this.datasetItemsTotal = response.dataset.total
        this.datasetOffset = 0
        this.datasetQuery = ''
        this.datasetCaptionState = 'all'
        if (response.items.length === 0 && response.dataset.total > 0) {
          await this.loadDatasetItems({ offset: 0, silent: true })
        }
        return response
      } catch (error) {
        if (inspectVersion === datasetInspectVersion) this.datasetError = message(error)
        return null
      } finally {
        if (inspectVersion === datasetInspectVersion) this.datasetLoading = false
      }
    },

    async loadDatasetItems(
      options: {
        offset?: number
        query?: string
        captionState?: string
        silent?: boolean
      } = {},
    ) {
      if (!this.dataset) return null
      const datasetId = this.dataset.id
      const requestVersion = ++datasetItemsRequestVersion
      const offset = options.offset ?? this.datasetOffset
      const query = options.query ?? this.datasetQuery
      const captionState = options.captionState ?? this.datasetCaptionState
      if (!options.silent) {
        datasetItemsLoadingVersion = requestVersion
        this.datasetLoading = true
      }
      this.datasetError = ''
      try {
        const response = await apiClient.listCaptionDatasetItems(datasetId, {
          offset,
          limit: this.datasetLimit,
          query,
          captionState,
        })
        if (requestVersion !== datasetItemsRequestVersion || this.dataset?.id !== datasetId) {
          return null
        }
        this.datasetItems = response.items
        this.datasetItemsTotal = response.total
        this.datasetOffset = response.offset
        this.datasetQuery = query
        this.datasetCaptionState = captionState
        return response
      } catch (error) {
        if (requestVersion === datasetItemsRequestVersion && this.dataset?.id === datasetId) {
          this.datasetError = message(error)
        }
        return null
      } finally {
        if (!options.silent && requestVersion === datasetItemsLoadingVersion) {
          this.datasetLoading = false
        }
      }
    },

    async setDatasetPageSize(size: number) {
      const normalized = [50, 100, 200].includes(size) ? size : 100
      this.datasetLimit = normalized
      return this.loadDatasetItems({ offset: 0 })
    },

    async saveDatasetItem(itemId: string, text: string, backupExisting = true) {
      if (!this.dataset) return null
      this.savingDatasetItemId = itemId
      this.datasetError = ''
      datasetItemsRequestVersion += 1
      this.datasetLoading = false
      try {
        const previous = this.datasetItems.find((item) => item.id === itemId)
        const updated = await apiClient.saveCaptionDatasetItem(this.dataset.id, itemId, {
          text,
          backupExisting,
        })
        const index = this.datasetItems.findIndex((item) => item.id === itemId)
        if (index >= 0) this.datasetItems[index] = updated
        if (this.dataset) {
          if (previous && !previous.captionExists && updated.captionExists) {
            this.dataset.withCaption += 1
            this.dataset.withoutCaption = Math.max(0, this.dataset.withoutCaption - 1)
          }
        }
        return updated
      } catch (error) {
        this.datasetError = message(error)
        return null
      } finally {
        this.savingDatasetItemId = ''
      }
    },

    clearDataset() {
      datasetInspectVersion += 1
      datasetItemsRequestVersion += 1
      this.datasetLoading = false
      this.dataset = null
      this.datasetItems = []
      this.datasetItemsTotal = 0
      this.datasetOffset = 0
      this.datasetQuery = ''
      this.datasetCaptionState = 'all'
      this.datasetError = ''
    },

    async loadJobs(options: { silent?: boolean } = {}) {
      if (!options.silent) this.jobsLoading = true
      this.jobsError = ''
      try {
        const response = await apiClient.listCaptionJobs(100)
        const existing = new Map(this.jobs.map((job) => [job.id, job]))
        this.jobs = response.jobs.map((job) => {
          const previous = existing.get(job.id)
          return previous && previous.revision > job.revision ? previous : job
        })
        const current = this.jobs.find((job) => job.id === this.currentJobId)
        if (
          current &&
          (!this.currentJob || current.revision >= this.currentJob.revision)
        ) {
          this.currentJob = current
        }
      } catch (error) {
        this.jobsError = message(error)
      } finally {
        this.jobsLoading = false
      }
    },

    patchJob(job: CaptionJobSummary) {
      const index = this.jobs.findIndex((item) => item.id === job.id)
      if (index >= 0 && this.jobs[index].revision > job.revision) return
      if (index >= 0) this.jobs[index] = job
      else this.jobs.unshift(job)
      if (
        job.id === this.currentJobId &&
        (!this.currentJob || job.revision >= this.currentJob.revision)
      ) {
        this.currentJob = job
      }
    },

    async createJob(request: CaptionJobCreateRequest) {
      this.starting = true
      this.currentError = ''
      try {
        const job = await apiClient.createCaptionJob(request)
        this.patchJob(job)
        return job
      } catch (error) {
        this.currentError = message(error)
        return null
      } finally {
        this.starting = false
      }
    },

    async selectJob(jobId: string) {
      this.stopObservation('idle')
      const version = observationVersion
      this.currentJobId = jobId
      this.currentJob = null
      this.currentItems = []
      this.currentItemsTotal = 0
      this.currentItemsOffset = 0
      this.currentItemsQuery = ''
      this.currentItemsState = ''
      currentItemsRequestVersion += 1
      lastResultRefreshAt = 0
      this.currentLogs = []
      this.currentLogsCursor = 0
      this.logsError = ''
      lastLogFetchAt = 0
      this.currentError = ''
      if (!jobId) return

      this.currentLoading = true
      try {
        const [job] = await Promise.all([
          apiClient.getCaptionJob(jobId),
          this.loadCurrentItems({ jobId, offset: 0, silent: true }),
          this.loadCurrentLogs({ jobId, silent: true }),
        ])
        if (version !== observationVersion || this.currentJobId !== jobId) return
        this.currentJob = job
        this.patchJob(job)
        refreshedItemsRevision = job.revision
        this.currentLoading = false
        if (isTerminal(job.state)) {
          this.streamStatus = 'ended'
        } else {
          this.connect(jobId)
        }
      } catch (error) {
        if (version === observationVersion && this.currentJobId === jobId) {
          this.currentError = message(error)
          this.streamStatus = 'error'
        }
      } finally {
        if (version === observationVersion) this.currentLoading = false
      }
    },

    async loadCurrentItems(
      options: {
        jobId?: string
        offset?: number
        query?: string
        state?: string
        silent?: boolean
      } = {},
    ) {
      const jobId = options.jobId || this.currentJobId
      if (!jobId) return null
      const requestVersion = ++currentItemsRequestVersion
      const offset = options.offset ?? this.currentItemsOffset
      const query = options.query ?? this.currentItemsQuery
      const state = options.state ?? this.currentItemsState
      if (!options.silent) {
        currentItemsLoadingVersion = requestVersion
        this.currentLoading = true
      }
      try {
        const response = await apiClient.listCaptionJobItems(jobId, {
          offset,
          limit: this.currentItemsLimit,
          query,
          state,
        })
        if (requestVersion !== currentItemsRequestVersion) return null
        if (this.currentJobId !== jobId && !options.jobId) return null
        if (this.currentJobId === jobId) {
          this.currentItems = response.items
          this.currentItemsTotal = response.total
          this.currentItemsOffset = response.offset
          this.currentItemsQuery = query
          this.currentItemsState = (state || '') as '' | CaptionItemState
          lastResultRefreshAt = Date.now()
        }
        return response
      } catch (error) {
        if (requestVersion === currentItemsRequestVersion && this.currentJobId === jobId) {
          this.currentError = message(error)
        }
        return null
      } finally {
        if (
          !options.silent &&
          requestVersion === currentItemsLoadingVersion &&
          this.currentJobId === jobId
        ) {
          this.currentLoading = false
        }
      }
    },

    async loadCurrentLogs(
      options: { jobId?: string; tail?: number; silent?: boolean } = {},
    ) {
      const jobId = options.jobId || this.currentJobId
      if (!jobId) return null
      if (!options.silent) this.logsLoading = true
      this.logsError = ''
      try {
        const response = await apiClient.getCaptionJobLogs(jobId, options.tail ?? 500)
        if (this.currentJobId === jobId) {
          this.currentLogs = response.lines
          this.currentLogsCursor = response.cursor
          lastLogFetchAt = Date.now()
        }
        return response
      } catch (error) {
        if (this.currentJobId === jobId) this.logsError = message(error)
        return null
      } finally {
        if (!options.silent && this.currentJobId === jobId) this.logsLoading = false
      }
    },

    async refreshCurrentJob(options: { silent?: boolean } = {}) {
      const jobId = this.currentJobId
      const version = observationVersion
      if (!jobId) return null
      if (!options.silent) this.currentLoading = true
      this.currentError = ''
      try {
        const job = await apiClient.getCaptionJob(jobId)
        if (version !== observationVersion || this.currentJobId !== jobId) return null
        this.patchJob(job)
        await Promise.all([
          this.loadCurrentItems({ offset: this.currentItemsOffset, silent: true }),
          this.loadCurrentLogs({ silent: true }),
        ])
        if (version === observationVersion && isTerminal(job.state)) this.stopObservation('ended')
        return job
      } catch (error) {
        if (this.currentJobId === jobId) this.currentError = message(error)
        return null
      } finally {
        if (!options.silent && this.currentJobId === jobId) this.currentLoading = false
      }
    },

    ingestProgress(job: CaptionJobSummary) {
      if (!job?.id || job.id !== this.currentJobId) return
      const previousRevision = this.currentJob?.revision ?? -1
      if (job.revision < previousRevision) return
      this.patchJob(job)
      this.lastEventAt = nowIso()
      this.streamError = ''
      const revisionChanged = job.revision > previousRevision && job.revision !== refreshedItemsRevision
      if (revisionChanged) {
        refreshedItemsRevision = job.revision
      }
      const terminal = isTerminal(job.state)
      if (terminal || Date.now() - lastLogFetchAt >= 2500) {
        lastLogFetchAt = Date.now()
        void this.loadCurrentLogs({ silent: true })
      }
      if (terminal) {
        this.stopObservation('ended')
        void this.loadCurrentItems({ offset: this.currentItemsOffset, silent: true })
        void this.loadJobs({ silent: true })
      } else if (revisionChanged) {
        const elapsed = Date.now() - lastResultRefreshAt
        if (elapsed >= RESULT_REFRESH_INTERVAL) {
          lastResultRefreshAt = Date.now()
          void this.loadCurrentItems({ offset: this.currentItemsOffset, silent: true })
        } else if (resultRefreshTimer === undefined) {
          resultRefreshTimer = window.setTimeout(() => {
            resultRefreshTimer = undefined
            if (this.currentJobId !== job.id || isTerminal(this.currentJob?.state)) return
            lastResultRefreshAt = Date.now()
            void this.loadCurrentItems({ offset: this.currentItemsOffset, silent: true })
          }, RESULT_REFRESH_INTERVAL - elapsed)
        }
      }
    },

    connect(jobId: string) {
      this.stopObservation('connecting')
      const version = observationVersion
      const isCurrent = () => version === observationVersion && this.currentJobId === jobId
      if (typeof EventSource === 'undefined') {
        this.startPolling(jobId, '浏览器不支持实时事件，已切换为轮询。')
        return
      }
      this.streamStatus = 'connecting'
      this.streamError = ''
      try {
        activeEvents = openCaptionJobEvents(jobId, this.currentJob?.revision || 0, {
          onOpen: () => {
            if (!isCurrent()) return
            this.streamStatus = 'live'
            this.streamError = ''
            this.lastEventAt = nowIso()
          },
          onProgress: (job) => {
            if (isCurrent()) this.ingestProgress(job)
          },
          onState: (job) => {
            if (isCurrent() && job?.modelId) this.ingestProgress(job)
          },
          onHeartbeat: () => {
            if (isCurrent()) this.lastEventAt = nowIso()
          },
          onError: () => {
            if (!isCurrent() || isTerminal(this.currentJob?.state)) return
            this.startPolling(jobId, '实时连接已中断，正在使用可靠轮询继续更新。')
          },
        })
      } catch (error) {
        this.startPolling(jobId, `无法建立实时连接：${message(error)}`)
      }
    },

    startPolling(jobId: string, reason = '') {
      this.stopObservation('polling')
      const version = observationVersion
      const isCurrent = () => version === observationVersion && this.currentJobId === jobId
      this.streamError = reason

      const poll = async () => {
        if (!isCurrent()) return
        try {
          const job = await apiClient.getCaptionJob(jobId)
          if (!isCurrent()) return
          this.ingestProgress(job)
        } catch (error) {
          if (!isCurrent()) return
          this.streamStatus = 'error'
          this.streamError = `轮询失败：${message(error)}`
        } finally {
          if (isCurrent()) pollTimer = window.setTimeout(() => void poll(), POLL_INTERVAL)
        }
      }
      void poll()
    },

    stopObservation(status: CaptionStreamStatus = 'idle') {
      observationVersion += 1
      this.currentLoading = false
      if (activeEvents) {
        activeEvents.close()
        activeEvents = null
      }
      if (pollTimer !== undefined) {
        window.clearTimeout(pollTimer)
        pollTimer = undefined
      }
      if (resultRefreshTimer !== undefined) {
        window.clearTimeout(resultRefreshTimer)
        resultRefreshTimer = undefined
      }
      this.streamStatus = status
    },

    async editCurrentItem(itemId: string, finalText: string) {
      if (!this.currentJobId) return null
      this.editingItemId = itemId
      this.currentError = ''
      try {
        const updated = await apiClient.editCaptionJobItem(this.currentJobId, itemId, finalText)
        const index = this.currentItems.findIndex((item) => item.id === itemId)
        if (index >= 0) this.currentItems[index] = updated
        return updated
      } catch (error) {
        this.currentError = message(error)
        return null
      } finally {
        this.editingItemId = ''
      }
    },

    async commitCurrentJob(request: CaptionCommitRequest) {
      if (!this.currentJobId) return null
      const jobId = this.currentJobId
      const version = observationVersion
      this.committing = true
      this.currentError = ''
      try {
        const job = await apiClient.commitCaptionJob(jobId, request)
        this.patchJob(job)
        if (version === observationVersion && this.currentJobId === jobId && !isTerminal(job.state)) {
          this.connect(jobId)
        }
        return job
      } catch (error) {
        this.currentError = message(error)
        return null
      } finally {
        this.committing = false
      }
    },

    async cancelCurrentJob() {
      if (!this.currentJobId) return null
      const jobId = this.currentJobId
      const version = observationVersion
      this.canceling = true
      this.currentError = ''
      try {
        const job = await apiClient.cancelCaptionJob(jobId)
        this.patchJob(job)
        if (version === observationVersion && this.currentJobId === jobId && isTerminal(job.state)) {
          this.stopObservation('ended')
        }
        return job
      } catch (error) {
        this.currentError = message(error)
        return null
      } finally {
        this.canceling = false
      }
    },
  },
})
