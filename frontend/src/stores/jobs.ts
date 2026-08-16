import { defineStore } from 'pinia'

import { ApiError, apiClient, openJobEvents } from '@/api/client'
import type { JobRecord, JobStartResult, JobState, TrainDraft } from '@/api/types'

const TERMINAL_STATES: JobState[] = ['succeeded', 'failed', 'terminated', 'canceled']
const MAX_STATIC_LOG_TAIL = 5000
const MAX_LIVE_LOG_LINES = 8000

export type JobStreamStatus = 'connecting' | 'live' | 'disconnected' | 'ended'

// EventSource is non-serializable, so it lives outside the reactive store.
let activeEvents: EventSource | null = null
let activeJobId = ''
let selectionVersion = 0

function isTerminal(state?: JobState) {
  return !!state && TERMINAL_STATES.includes(state)
}

function eventTimestamp() {
  return new Date().toISOString()
}

export const useJobsStore = defineStore('jobs', {
  state: () => ({
    jobs: [] as JobRecord[],
    selectedJobId: '',
    selectedJob: null as JobRecord | null,
    logLines: [] as string[],
    streaming: false,
    streamStatus: 'disconnected' as JobStreamStatus,
    lastEventAt: '',
    streamError: '',
    listRefreshError: '',
    lastListLoadedAt: '',
    loading: false,
    starting: false,
    terminating: false,
    error: '',
    startResult: null as JobStartResult | null,
  }),
  getters: {
    selectedJobFromList(state) {
      return state.jobs.find((job) => job.id === state.selectedJobId) || state.selectedJob
    },
  },
  actions: {
    async loadJobs(options: { silent?: boolean } = {}) {
      const silent = options.silent ?? false
      if (!silent) {
        this.loading = true
        this.error = ''
      }
      this.listRefreshError = ''
      try {
        const data = await apiClient.listJobs()
        this.jobs = data.jobs
        this.lastListLoadedAt = eventTimestamp()
        if (!this.selectedJobId && data.jobs.length > 0) {
          await this.selectJob(data.jobs[0].id)
          return
        }

        const selectedJob = data.jobs.find((job) => job.id === this.selectedJobId)
        if (selectedJob) this.selectedJob = selectedJob
        if (selectedJob && isTerminal(selectedJob.state) && this.streamStatus !== 'ended') {
          this.selectedJob = selectedJob
          this.disconnect('ended')
          this.streamError = ''
          void this.loadStaticLogs(selectedJob.id)
        }
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error)
        if (silent && this.jobs.length > 0) {
          this.listRefreshError = `任务列表刷新失败，正在显示上次结果：${message}`
        } else {
          this.error = message
        }
      } finally {
        if (!silent) this.loading = false
      }
    },

    async selectJob(jobId: string) {
      if (!jobId) {
        selectionVersion += 1
        this.disconnect('disconnected')
        this.selectedJobId = ''
        this.selectedJob = null
        this.logLines = []
        this.lastEventAt = ''
        this.streamError = ''
        return
      }
      if (jobId === this.selectedJobId && activeEvents && activeJobId === jobId) {
        return
      }
      if (
        jobId === this.selectedJobId &&
        this.selectedJob?.id === jobId &&
        isTerminal(this.selectedJob.state)
      ) {
        this.disconnect('ended')
        this.streamError = ''
        if (this.logLines.length === 0) await this.loadStaticLogs(jobId)
        return
      }

      this.disconnect('disconnected')
      const currentSelectionVersion = ++selectionVersion
      this.selectedJobId = jobId
      this.logLines = []
      this.error = ''
      this.lastEventAt = ''
      this.streamError = ''

      try {
        const selectedJob = await apiClient.getJob(jobId)
        if (currentSelectionVersion !== selectionVersion || this.selectedJobId !== jobId) return
        this.selectedJob = selectedJob
      } catch (error) {
        if (currentSelectionVersion === selectionVersion && this.selectedJobId === jobId) {
          this.error = error instanceof Error ? error.message : String(error)
        }
        return
      }

      if (isTerminal(this.selectedJob.state)) {
        this.disconnect('ended')
        await this.loadStaticLogs(jobId)
      } else {
        this.connectStream(jobId)
      }
    },

    async loadStaticLogs(jobId: string) {
      try {
        const logs = await apiClient.getJobLogs(jobId, MAX_STATIC_LOG_TAIL)
        if (this.selectedJobId === jobId) this.logLines = logs.lines
      } catch (error) {
        if (this.selectedJobId === jobId) {
          this.error = error instanceof Error ? error.message : String(error)
        }
      }
    },

    connectStream(jobId: string) {
      this.streaming = false
      this.streamStatus = 'connecting'
      this.streamError = ''
      activeJobId = jobId

      try {
        activeEvents = openJobEvents(jobId, {
          onOpen: () => {
            if (activeJobId !== jobId || this.selectedJobId !== jobId) return
            this.streaming = true
            this.streamStatus = 'live'
            this.streamError = ''
            this.lastEventAt = eventTimestamp()
          },
          onLog: (line) => {
            if (activeJobId !== jobId || this.selectedJobId !== jobId) return
            this.streaming = true
            this.streamStatus = 'live'
            this.streamError = ''
            this.lastEventAt = eventTimestamp()
            this.logLines.push(line)
            if (this.logLines.length > MAX_LIVE_LOG_LINES) {
              this.logLines.splice(0, this.logLines.length - MAX_LIVE_LOG_LINES)
            }
          },
          onState: (job) => {
            if (activeJobId !== jobId || this.selectedJobId !== jobId) return
            this.lastEventAt = eventTimestamp()
            this.patchJob(job)
            this.selectedJob = job
            if (isTerminal(job.state)) {
              // Reconcile against the authoritative log, then close the stream.
              // A terminal stream is complete, not disconnected.
              void this.loadStaticLogs(jobId)
              this.disconnect('ended')
              this.streamError = ''
              return
            }
            this.streaming = true
            this.streamStatus = 'live'
            this.streamError = ''
          },
          onError: () => {
            // The backend cannot resume from a cursor. Stop EventSource's
            // automatic reconnect (which would replay the entire log and
            // duplicate buffered lines) and retain a one-shot static snapshot.
            if (activeJobId === jobId && !isTerminal(this.selectedJob?.state)) {
              this.disconnect('disconnected')
              this.streamError = '实时日志连接已中断。重新连接时将从头加载日志。'
              void this.loadStaticLogs(jobId)
            }
          },
        })
      } catch (error) {
        activeEvents = null
        activeJobId = ''
        this.streaming = false
        this.streamStatus = 'disconnected'
        this.streamError = error instanceof Error ? error.message : String(error)
      }
    },

    disconnect(status?: JobStreamStatus) {
      if (activeEvents) {
        activeEvents.close()
        activeEvents = null
      }
      activeJobId = ''
      this.streaming = false
      this.streamStatus = status ?? (isTerminal(this.selectedJob?.state) ? 'ended' : 'disconnected')
    },

    async reconnectSelectedJob() {
      const jobId = this.selectedJobId
      if (!jobId) return

      const reconnectVersion = ++selectionVersion
      this.disconnect()
      this.streamStatus = 'connecting'
      this.streamError = ''

      try {
        const job = await apiClient.getJob(jobId)
        if (reconnectVersion !== selectionVersion || this.selectedJobId !== jobId) return

        this.selectedJob = job
        this.patchJob(job)
        if (isTerminal(job.state)) {
          this.disconnect('ended')
          this.logLines = []
          await this.loadStaticLogs(jobId)
          return
        }

        // /events always replays from cursor 0. Clear the old buffer before
        // opening a replacement stream so replayed lines are not duplicated.
        this.logLines = []
        this.lastEventAt = ''
        this.connectStream(jobId)
      } catch (error) {
        if (reconnectVersion !== selectionVersion || this.selectedJobId !== jobId) return
        this.disconnect('disconnected')
        this.streamError = error instanceof Error ? error.message : String(error)
      }
    },

    patchJob(job: JobRecord) {
      const index = this.jobs.findIndex((item) => item.id === job.id)
      if (index >= 0) this.jobs[index] = job
    },

    async startJob(draft: TrainDraft) {
      this.starting = true
      this.error = ''
      this.startResult = null
      try {
        this.startResult = await apiClient.startJob(draft)
        if (this.startResult.job) {
          await this.loadJobs()
          await this.selectJob(this.startResult.job.id)
        }
      } catch (error) {
        if (error instanceof ApiError && error.body && typeof error.body === 'object') {
          const payload = error.body as Partial<JobStartResult>
          if (payload.compile) this.startResult = payload as JobStartResult
        }
        this.error = error instanceof Error ? error.message : String(error)
      } finally {
        this.starting = false
      }
      return this.startResult
    },

    async terminateSelectedJob() {
      if (!this.selectedJobId) return
      const jobId = this.selectedJobId
      this.terminating = true
      this.error = ''
      try {
        const terminatedJob = await apiClient.terminateJob(jobId)
        this.patchJob(terminatedJob)
        if (this.selectedJobId === jobId) {
          this.selectedJob = terminatedJob
          if (isTerminal(terminatedJob.state)) {
            this.disconnect('ended')
            this.streamError = ''
            void this.loadStaticLogs(jobId)
          }
        }
      } catch (error) {
        if (this.selectedJobId === jobId) {
          this.error = error instanceof Error ? error.message : String(error)
        }
      } finally {
        this.terminating = false
      }
    },
  },
})
