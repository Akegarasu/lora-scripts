import type {
  CaptionCommitRequest,
  CaptionDatasetInspectRequest,
  CaptionDatasetInspectResponse,
  CaptionDatasetItem,
  CaptionDatasetItemsResponse,
  CaptionJobCreateRequest,
  CaptionJobItem,
  CaptionJobItemsResponse,
  CaptionJobListResponse,
  CaptionJobSummary,
  CaptionModelsResponse,
  CompileResult,
  FilesResponse,
  GpuInfo,
  HealthResponse,
  JobListResponse,
  JobLogResponse,
  JobMetricBatch,
  JobMetricCursor,
  JobMetricsResponse,
  JobMetricStateEvent,
  JobRecord,
  JobStartResult,
  SafetensorsMetadataResponse,
  TagEditorApplyRequest,
  TagEditorChangeSetListResponse,
  TagEditorChangeSetSummary,
  TagEditorChangeResultsResponse,
  TagEditorDatasetItemDetail,
  TagEditorInspectRequest,
  TagEditorInspectResponse,
  TagEditorItemsQuery,
  TagEditorItemsResponse,
  TagEditorPreviewRequest,
  TagEditorPreviewResponse,
  TagEditorTagSuggestionsResponse,
  TrainerParamsResponse,
  TrainersResponse,
  TrainDraft,
} from './types'

const API_BASE = import.meta.env.VITE_API_BASE || ''

export class ApiError extends Error {
  readonly status: number
  readonly body: unknown

  constructor(status: number, message: string, body: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}

function errorMessage(body: unknown, fallback: string) {
  if (!body || typeof body !== 'object') return fallback
  const payload = body as Record<string, unknown>
  if (typeof payload.detail === 'string') return payload.detail
  if (Array.isArray(payload.detail)) {
    const details = payload.detail
      .map((item) => {
        if (!item || typeof item !== 'object') return ''
        const detail = item as Record<string, unknown>
        return typeof detail.msg === 'string' ? detail.msg : ''
      })
      .filter(Boolean)
    if (details.length) return details.join('；')
  }
  const compile = payload.compile
  if (compile && typeof compile === 'object') {
    const errors = (compile as Record<string, unknown>).errors
    if (Array.isArray(errors)) {
      const messages = errors
        .map((item) => {
          if (!item || typeof item !== 'object') return ''
          const message = (item as Record<string, unknown>).message
          return typeof message === 'string' ? message : ''
        })
        .filter(Boolean)
      if (messages.length) return messages.join('；')
    }
  }
  return fallback
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers || {}),
    },
    ...init,
  })

  if (!response.ok) {
    const raw = await response.text()
    let body: unknown = raw
    if (raw) {
      try {
        body = JSON.parse(raw) as unknown
      } catch {
        /* keep the plain-text body */
      }
    }
    const fallback = raw || `${response.status} ${response.statusText}`
    throw new ApiError(response.status, errorMessage(body, fallback), body)
  }

  return response.json() as Promise<T>
}

export const apiClient = {
  getHealth() {
    return request<HealthResponse>('/api/v2/health')
  },
  listTrainers() {
    return request<TrainersResponse>('/api/v2/trainers')
  },
  getTrainerParams(trainerId: string, view: string) {
    return request<TrainerParamsResponse>(
      `/api/v2/trainers/${encodeURIComponent(trainerId)}/params?view=${encodeURIComponent(view)}`,
    )
  },
  compileDraft(draft: TrainDraft, options: { persist?: boolean; validatePaths?: boolean } = {}) {
    const persist = options.persist ?? false
    const validatePaths = options.validatePaths ?? false
    return request<CompileResult>(`/api/v2/compile?persist=${persist}&validate_paths=${validatePaths}`, {
      method: 'POST',
      body: JSON.stringify(draft),
    })
  },
  startJob(draft: TrainDraft, options: { validatePaths?: boolean } = {}) {
    const validatePaths = options.validatePaths ?? true
    return request<JobStartResult>(`/api/v2/jobs?validate_paths=${validatePaths}`, {
      method: 'POST',
      body: JSON.stringify(draft),
    })
  },
  listJobs(limit = 200) {
    return request<JobListResponse>(`/api/v2/jobs?limit=${limit}`)
  },
  getJob(jobId: string) {
    return request<JobRecord>(`/api/v2/jobs/${encodeURIComponent(jobId)}`)
  },
  getJobLogs(jobId: string, tail = 500) {
    return request<JobLogResponse>(`/api/v2/jobs/${encodeURIComponent(jobId)}/logs?tail=${tail}`)
  },
  getJobMetrics(
    jobId: string,
    options: { cursor?: JobMetricCursor; maxPoints?: number; tags?: string[] } = {},
  ) {
    const params = new URLSearchParams()
    if (options.cursor !== undefined && options.cursor !== '') {
      params.set('cursor', String(options.cursor))
    }
    params.set('max_points', String(options.maxPoints ?? 5000))
    if (options.tags?.length) params.set('tags', options.tags.join(','))
    return request<JobMetricsResponse>(
      `/api/v2/jobs/${encodeURIComponent(jobId)}/metrics?${params.toString()}`,
    )
  },
  terminateJob(jobId: string) {
    return request<JobRecord>(`/api/v2/jobs/${encodeURIComponent(jobId)}/terminate`, { method: 'POST' })
  },
  browseFiles(options: { kind?: string; root?: string; path?: string } = {}) {
    const params = new URLSearchParams({
      kind: options.kind || 'file',
      root: options.root || 'workspace',
      path: options.path || '',
    })
    return request<FilesResponse>(`/api/v2/files?${params.toString()}`)
  },
  getSafetensorsMetadata(path: string) {
    const params = new URLSearchParams({ path })
    return request<SafetensorsMetadataResponse>(
      `/api/v2/files/safetensors-metadata?${params.toString()}`,
    )
  },
  listGpus() {
    return request<{ gpus: GpuInfo[]; error?: string }>('/api/v2/devices/gpus')
  },
  listCaptionModels() {
    return request<CaptionModelsResponse>('/api/v2/caption/models')
  },
  unloadCaptionModels() {
    return request<{ status: string }>('/api/v2/caption/models/unload', { method: 'POST' })
  },
  inspectCaptionDataset(payload: CaptionDatasetInspectRequest) {
    return request<CaptionDatasetInspectResponse>('/api/v2/caption/datasets/inspect', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  },
  listCaptionDatasetItems(
    datasetId: string,
    options: { offset?: number; limit?: number; query?: string; captionState?: string } = {},
  ) {
    const params = new URLSearchParams({
      offset: String(options.offset ?? 0),
      limit: String(options.limit ?? 100),
      query: options.query || '',
      caption_state: options.captionState || 'all',
    })
    return request<CaptionDatasetItemsResponse>(
      `/api/v2/caption/datasets/${encodeURIComponent(datasetId)}/items?${params.toString()}`,
    )
  },
  saveCaptionDatasetItem(
    datasetId: string,
    itemId: string,
    payload: { text: string; backupExisting?: boolean },
  ) {
    return request<CaptionDatasetItem>(
      `/api/v2/caption/datasets/${encodeURIComponent(datasetId)}/items/${encodeURIComponent(itemId)}/caption`,
      { method: 'PUT', body: JSON.stringify(payload) },
    )
  },
  createCaptionJob(payload: CaptionJobCreateRequest) {
    return request<CaptionJobSummary>('/api/v2/caption/jobs', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  },
  listCaptionJobs(limit = 100) {
    return request<CaptionJobListResponse>(`/api/v2/caption/jobs?limit=${limit}`)
  },
  getCaptionJob(jobId: string) {
    return request<CaptionJobSummary>(`/api/v2/caption/jobs/${encodeURIComponent(jobId)}`)
  },
  getCaptionJobLogs(jobId: string, tail = 500) {
    return request<JobLogResponse>(
      `/api/v2/caption/jobs/${encodeURIComponent(jobId)}/logs?tail=${tail}`,
    )
  },
  listCaptionJobItems(
    jobId: string,
    options: { offset?: number; limit?: number; query?: string; state?: string } = {},
  ) {
    const params = new URLSearchParams({
      offset: String(options.offset ?? 0),
      limit: String(options.limit ?? 100),
      query: options.query || '',
    })
    if (options.state) params.set('state', options.state)
    return request<CaptionJobItemsResponse>(
      `/api/v2/caption/jobs/${encodeURIComponent(jobId)}/items?${params.toString()}`,
    )
  },
  editCaptionJobItem(jobId: string, itemId: string, finalText: string) {
    return request<CaptionJobItem>(
      `/api/v2/caption/jobs/${encodeURIComponent(jobId)}/items/${encodeURIComponent(itemId)}`,
      { method: 'PATCH', body: JSON.stringify({ finalText }) },
    )
  },
  commitCaptionJob(jobId: string, payload: CaptionCommitRequest) {
    return request<CaptionJobSummary>(
      `/api/v2/caption/jobs/${encodeURIComponent(jobId)}/commit`,
      { method: 'POST', body: JSON.stringify(payload) },
    )
  },
  cancelCaptionJob(jobId: string) {
    return request<CaptionJobSummary>(
      `/api/v2/caption/jobs/${encodeURIComponent(jobId)}/cancel`,
      { method: 'POST' },
    )
  },
  inspectTagEditorDataset(payload: TagEditorInspectRequest) {
    return request<TagEditorInspectResponse>('/api/v2/tag-editor/datasets/inspect', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  },
  listTagEditorDatasetItems(datasetId: string, options: TagEditorItemsQuery = {}) {
    const params = new URLSearchParams({
      offset: String(options.offset ?? 0),
      limit: String(options.limit ?? 100),
      query: options.query || '',
      state: options.state || 'all',
      sort: options.sort || 'path_asc',
    })
    return request<TagEditorItemsResponse>(
      `/api/v2/tag-editor/datasets/${encodeURIComponent(datasetId)}/items?${params.toString()}`,
    )
  },
  getTagEditorDatasetItem(datasetId: string, itemId: string) {
    return request<TagEditorDatasetItemDetail>(
      `/api/v2/tag-editor/datasets/${encodeURIComponent(datasetId)}/items/${encodeURIComponent(itemId)}`,
    )
  },
  previewTagEditorChanges(datasetId: string, payload: TagEditorPreviewRequest) {
    return request<TagEditorPreviewResponse>(
      `/api/v2/tag-editor/datasets/${encodeURIComponent(datasetId)}/changes/preview`,
      { method: 'POST', body: JSON.stringify(payload) },
    )
  },
  applyTagEditorChanges(datasetId: string, payload: TagEditorApplyRequest) {
    return request<TagEditorChangeSetSummary>(
      `/api/v2/tag-editor/datasets/${encodeURIComponent(datasetId)}/changes/apply`,
      { method: 'POST', body: JSON.stringify(payload) },
    )
  },
  listTagEditorChanges(limit = 100) {
    return request<TagEditorChangeSetListResponse>(`/api/v2/tag-editor/changes?limit=${limit}`)
  },
  getTagEditorChange(changeSetId: string) {
    return request<TagEditorChangeSetSummary>(
      `/api/v2/tag-editor/changes/${encodeURIComponent(changeSetId)}`,
    )
  },
  listTagEditorChangeResults(
    changeSetId: string,
    options: { offset?: number; limit?: number } = {},
  ) {
    const params = new URLSearchParams({
      offset: String(options.offset ?? 0),
      limit: String(options.limit ?? 100),
    })
    return request<TagEditorChangeResultsResponse>(
      `/api/v2/tag-editor/changes/${encodeURIComponent(changeSetId)}/results?${params.toString()}`,
    )
  },
  rollbackTagEditorChange(changeSetId: string) {
    return request<TagEditorChangeSetSummary>(
      `/api/v2/tag-editor/changes/${encodeURIComponent(changeSetId)}/rollback`,
      { method: 'POST' },
    )
  },
  suggestTagEditorTags(datasetId: string, options: { query?: string; limit?: number } = {}) {
    const params = new URLSearchParams({
      query: options.query || '',
      limit: String(options.limit ?? 50),
    })
    return request<TagEditorTagSuggestionsResponse>(
      `/api/v2/tag-editor/datasets/${encodeURIComponent(datasetId)}/tag-suggestions?${params.toString()}`,
    )
  },
}

export function apiAssetUrl(path: string): string {
  if (!path) return ''
  if (/^https?:\/\//i.test(path)) return path
  return `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`
}

export function outputFileUrl(path: string): string {
  const params = new URLSearchParams({ path })
  return apiAssetUrl(`/api/v2/files/content?${params.toString()}`)
}

export interface JobEventHandlers {
  onOpen?: () => void
  onLog?: (line: string) => void
  onState?: (job: JobRecord) => void
  onError?: (event: Event) => void
}

/**
 * Open a Server-Sent Events stream for a job's live logs and state changes.
 * The backend replays the whole log from the start of the stream, so callers
 * should clear their buffer before connecting. Remember to call `.close()`.
 */
export function openJobEvents(jobId: string, handlers: JobEventHandlers): EventSource {
  const source = new EventSource(`${API_BASE}/api/v2/jobs/${encodeURIComponent(jobId)}/events`)

  source.onopen = () => handlers.onOpen?.()

  source.addEventListener('log', (event) => {
    try {
      const data = JSON.parse((event as MessageEvent).data)
      if (typeof data.line === 'string') handlers.onLog?.(data.line)
    } catch {
      /* ignore malformed frame */
    }
  })

  source.addEventListener('state', (event) => {
    try {
      const data = JSON.parse((event as MessageEvent).data) as JobRecord
      handlers.onState?.(data)
    } catch {
      /* ignore malformed frame */
    }
  })

  source.onerror = (event) => handlers.onError?.(event)
  return source
}

export interface JobMetricEventHandlers {
  onOpen?: () => void
  onSnapshot?: (snapshot: JobMetricsResponse) => void
  onMetric?: (batch: JobMetricBatch) => void
  onState?: (state: JobMetricStateEvent) => void
  onHeartbeat?: () => void
  onError?: (event: Event) => void
}

function parseMetricFrame<T>(event: Event): T | null {
  const raw = (event as MessageEvent).data
  if (typeof raw !== 'string' || !raw.trim()) return null
  try {
    return JSON.parse(raw) as T
  } catch {
    return null
  }
}

/** Open the resumable metric stream associated with one job. */
export function openJobMetricEvents(
  jobId: string,
  cursor: JobMetricCursor | undefined,
  handlers: JobMetricEventHandlers,
): EventSource {
  const params = new URLSearchParams()
  if (cursor !== undefined && cursor !== '') {
    // `cursor` is canonical; `after` keeps the client compatible with the
    // earlier endpoint draft while backends converge on the final contract.
    params.set('cursor', String(cursor))
    params.set('after', String(cursor))
  }
  const query = params.size ? `?${params.toString()}` : ''
  const source = new EventSource(
    `${API_BASE}/api/v2/jobs/${encodeURIComponent(jobId)}/metric-events${query}`,
  )

  source.onopen = () => handlers.onOpen?.()
  source.addEventListener('snapshot', (event) => {
    const payload = parseMetricFrame<JobMetricsResponse>(event)
    if (payload) handlers.onSnapshot?.(payload)
  })
  source.addEventListener('metric', (event) => {
    const payload = parseMetricFrame<JobMetricBatch>(event)
    if (payload) handlers.onMetric?.(payload)
  })
  source.addEventListener('state', (event) => {
    const payload = parseMetricFrame<JobMetricStateEvent>(event)
    if (payload) handlers.onState?.(payload)
  })
  source.addEventListener('heartbeat', () => handlers.onHeartbeat?.())
  source.onmessage = (event) => {
    const payload = parseMetricFrame<JobMetricBatch>(event)
    if (payload) handlers.onMetric?.(payload)
  }
  source.onerror = (event) => handlers.onError?.(event)
  return source
}

export interface CaptionJobEventHandlers {
  onOpen?: () => void
  onProgress?: (job: CaptionJobSummary) => void
  onState?: (job: CaptionJobSummary) => void
  onHeartbeat?: () => void
  onError?: (event: Event) => void
}

function parseCaptionFrame(event: Event): CaptionJobSummary | null {
  const raw = (event as MessageEvent).data
  if (typeof raw !== 'string' || !raw.trim()) return null
  try {
    return JSON.parse(raw) as CaptionJobSummary
  } catch {
    return null
  }
}

/** Open the resumable Caption task progress stream. */
export function openCaptionJobEvents(
  jobId: string,
  after: number,
  handlers: CaptionJobEventHandlers,
): EventSource {
  const params = new URLSearchParams()
  if (after > 0) params.set('after', String(after))
  const query = params.size ? `?${params.toString()}` : ''
  const source = new EventSource(
    `${API_BASE}/api/v2/caption/jobs/${encodeURIComponent(jobId)}/events${query}`,
  )
  source.onopen = () => handlers.onOpen?.()
  source.addEventListener('progress', (event) => {
    const job = parseCaptionFrame(event)
    if (job) handlers.onProgress?.(job)
  })
  source.addEventListener('state', (event) => {
    const job = parseCaptionFrame(event)
    if (job) handlers.onState?.(job)
  })
  source.addEventListener('heartbeat', () => handlers.onHeartbeat?.())
  source.onerror = (event) => handlers.onError?.(event)
  return source
}
