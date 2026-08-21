export type ParamPriority = 'required' | 'recommended' | 'advanced' | 'dangerous' | 'hidden' | 'raw'

export interface HealthResponse {
  status: string
  version: string
  channel: 'development' | 'prerelease' | 'stable'
  tag: string
  frontend: {
    requiredVersion: string
    installedVersion?: string | null
    buildCommit?: string | null
    builtAt?: string | null
    source?: string | null
  }
  python: string
  devMode: boolean
}

export interface TrainerSummary {
  id: string
  title: string
  family: string
  task: string
  script: string
  status: string
  datasetDefaults: Record<string, unknown>
}

export interface ParamSource {
  script?: string
  module?: string
  function?: string
}

export interface ParamDefinition {
  name: string
  flags: string[]
  type: string
  itemType?: string
  default?: unknown
  effectiveDefault?: unknown
  choices?: unknown[]
  nargs?: string | number
  action?: string
  required?: boolean
  help?: string
  source?: ParamSource
  label?: string
  description?: string
  group: string
  priority: ParamPriority
  control?: string
  fileKind?: string
  min?: number
  max?: number
  step?: number
  precision?: number
  placeholder?: string
  omitIfZero?: boolean
  deprecated?: boolean
  sensitive?: boolean
  advanced?: boolean
  hidden?: boolean
  rules?: Record<string, unknown>[]
  extra?: Record<string, unknown>
}

export interface ParamGroup {
  id: string
  title: string
  description?: string
  order: number
  params: ParamDefinition[]
}

export interface TrainerParamsResponse {
  trainerId: string
  view: string
  groups: ParamGroup[]
  manifestHash: string
}

export interface TrainersResponse {
  trainers: TrainerSummary[]
  manifestHash: string
}

export interface TrainDraft {
  trainerId: string
  name?: string
  modelAssets: Record<string, unknown>
  dataset: Record<string, unknown>
  params: Record<string, unknown>
  runtime: {
    gpuIds: string[]
    numCpuThreadsPerProcess: number
  }
  sample: SampleDraft
}

export interface SamplePromptDraft {
  prompt: string
  negativePrompt?: string
  width?: number
  height?: number
  seed?: number
  steps?: number
  cfgScale?: number
  guidanceScale?: number
}

export interface SampleDraft {
  enabled: boolean
  everyNEpochs?: number
  everyNSteps?: number
  sampler?: string
  prompts: SamplePromptDraft[]
}

export interface ValidationMessage {
  severity: 'error' | 'warning' | 'info'
  code: string
  message: string
  field?: string
}

export interface CompileResult {
  runId?: string
  trainerId: string
  manifestHash: string
  artifacts?: Record<string, string>
  command: string[]
  trainConfig?: string
  datasetConfig?: string
  samplePrompts?: string
  warnings: ValidationMessage[]
  errors: ValidationMessage[]
}

export type JobState = 'created' | 'queued' | 'running' | 'succeeded' | 'failed' | 'terminating' | 'terminated' | 'canceled'

export interface JobRecord {
  id: string
  runId: string
  trainerId: string
  name?: string
  state: JobState
  command: string[]
  env?: Record<string, string>
  artifacts?: Record<string, string>
  logPath?: string
  createdAt: string
  startedAt?: string
  endedAt?: string
  exitCode?: number
  errorMessage?: string
}

export interface JobListResponse {
  jobs: JobRecord[]
}

export interface JobStartResult {
  job?: JobRecord
  compile: CompileResult
}

export interface JobLogResponse {
  jobId: string
  cursor: number
  lines: string[]
}

export type JobMetricCursor = string | number

export interface JobMetricPoint {
  seq: number
  step: number
  wallTime: number
  value: number
}

export interface JobMetricSeries {
  tag: string
  points: JobMetricPoint[]
}

export interface JobMetricsResponse {
  jobId: string
  cursor: JobMetricCursor
  sourcePath?: string
  available?: boolean
  pointCount?: number
  errors?: string[]
  tags: string[]
  series: JobMetricSeries[]
}

/**
 * Live metric frames intentionally accept both the canonical batched `series`
 * shape and the compact single-series/single-point shape. This keeps the UI
 * compatible with streamed tail records without weakening the REST snapshot.
 */
export interface JobMetricBatch {
  jobId?: string
  cursor?: JobMetricCursor
  sourcePath?: string
  available?: boolean
  pointCount?: number
  errors?: string[]
  tags?: string[]
  series?: JobMetricSeries[]
  events?: JobMetricBatch[]
  tag?: string
  point?: JobMetricPoint
  points?: JobMetricPoint[]
}

export interface JobMetricStateEvent {
  state?: JobState | 'missing' | 'ended'
  cursor?: JobMetricCursor
}

export interface FileItem {
  name: string
  path: string
  type: 'file' | 'dir'
  size: number
  modifiedAt: string
}

export interface FilesResponse {
  items: FileItem[]
}

export interface FileManagerCapability {
  available: boolean
  platform: string
  fileManager?: string | null
  reason?: string | null
}

export interface RevealOutputPathResponse {
  status: string
  path: string
}

export interface SafetensorsMetadataResponse {
  name: string
  path: string
  size: number
  modifiedAt: string
  tensorCount: number
  metadata: Record<string, string>
}

export interface GpuInfo {
  id: string
  name: string
  vramTotal: number
  vramFree: number
}

export type CaptionOutputMode = 'tags' | 'caption' | 'hybrid'
export type CaptionModelStatus = 'ready' | 'downloadable' | 'unavailable' | 'misconfigured'
export type CaptionModelProvider = 'local-onnx' | 'local-transformers' | 'remote'

export interface CaptionModelParam {
  name: string
  label: string
  description: string
  type: 'string' | 'integer' | 'number' | 'boolean' | 'choice' | 'multiline'
  default?: unknown
  choices?: unknown[]
  min?: number
  max?: number
  step?: number
  advanced?: boolean
  required?: boolean
  placeholder?: string
}

export interface CaptionModelParamGroup {
  id: string
  title: string
  description?: string
  params: CaptionModelParam[]
}

export interface CaptionModelCapabilities {
  prompt: boolean
  scores: boolean
  categories: boolean
  batch: boolean
  languages: string[]
  devices: string[]
}

export interface CaptionModelSummary {
  id: string
  title: string
  description: string
  family: string
  engine: string
  provider: CaptionModelProvider
  repoId?: string
  outputModes: CaptionOutputMode[]
  defaultOutputMode: CaptionOutputMode
  status: CaptionModelStatus
  statusReason?: string
  missingDependencies: string[]
  capabilities: CaptionModelCapabilities
  paramGroups: CaptionModelParamGroup[]
  recommendedVramGb?: number
  license?: string
  homepage?: string
  minTransformers?: string
  gated: boolean
  requiresHfToken: boolean
  trustRemoteCode: boolean
  warnings: string[]
  experimental?: boolean
}

export interface CaptionModelsResponse {
  models: CaptionModelSummary[]
  defaultModelId: string
}

export interface CaptionDatasetInspectRequest {
  root: 'train' | 'datasets' | 'workspace'
  path: string
  recursive: boolean
  captionExtension: string
  maxImages: number
  initialLimit?: number
}

export interface CaptionDatasetItem {
  id: string
  name: string
  relativePath: string
  width?: number
  height?: number
  captionExists: boolean
  captionText: string
  captionTruncated: boolean
  writable: boolean
  error?: string
  errorCode?: string
  thumbnailUrl: string
}

export interface CaptionDatasetSummary {
  id: string
  root: string
  path: string
  recursive: boolean
  captionExtension: string
  total: number
  withCaption: number
  withoutCaption: number
  truncated: boolean
  createdAt: string
}

export interface CaptionDatasetInspectResponse {
  dataset: CaptionDatasetSummary
  items: CaptionDatasetItem[]
}

export interface CaptionDatasetItemsResponse {
  datasetId: string
  total: number
  offset: number
  limit: number
  items: CaptionDatasetItem[]
}

export interface CaptionPromptOptions {
  instruction: string
  language: string
}

export interface CaptionPostprocessOptions {
  additionalTags: string[]
  excludeTags: string[]
  prefix: string
  suffix: string
  separator: string
  deduplicate: boolean
  replaceUnderscore: boolean
  replaceUnderscoreExcludes: string[]
  escapeTags: boolean
  includeConfidence: boolean
}

export type CaptionConflictPolicy = 'skip' | 'fill_empty' | 'overwrite' | 'prepend' | 'append'

export interface CaptionOutputOptions {
  stageBeforeWrite: boolean
  conflictPolicy: CaptionConflictPolicy
  backupExisting: boolean
  saveRawResult: boolean
}

export interface CaptionRuntimeOptions {
  device: 'auto' | 'cpu' | 'cuda'
  dtype: 'auto' | 'float32' | 'float16' | 'bfloat16'
  batchSize: number
  keepModelLoaded: boolean
}

export interface CaptionJobCreateRequest {
  name?: string
  datasetId: string
  itemIds?: string[]
  modelId: string
  outputMode: CaptionOutputMode
  params: Record<string, unknown>
  prompt: CaptionPromptOptions
  postprocess: CaptionPostprocessOptions
  output: CaptionOutputOptions
  runtime: CaptionRuntimeOptions
}

export type CaptionJobState =
  | 'created'
  | 'queued'
  | 'running'
  | 'loading'
  | 'generating'
  | 'awaiting_review'
  | 'committing'
  | 'succeeded'
  | 'partial'
  | 'failed'
  | 'canceling'
  | 'canceled'
  | 'interrupted'

export interface CaptionJobSummary {
  id: string
  name?: string
  modelId: string
  modelTitle: string
  outputMode: CaptionOutputMode
  reviewMode: boolean
  detailsState: 'available' | 'compacted' | 'expired'
  state: CaptionJobState
  message: string
  revision: number
  datasetId: string
  total: number
  processed: number
  succeeded: number
  failed: number
  skipped: number
  conflicts: number
  written: number
  createdAt: string
  startedAt?: string
  endedAt?: string
  errorMessage?: string
  logPath?: string
}

export interface CaptionJobListResponse {
  jobs: CaptionJobSummary[]
}

export type CaptionItemState =
  | 'pending'
  | 'running'
  | 'succeeded'
  | 'failed'
  | 'skipped'
  | 'conflict'
  | 'canceled'

export interface CaptionTag {
  text: string
  score?: number | null
  category?: string | null
}

export interface CaptionJobItem {
  id: string
  index: number
  name: string
  relativePath: string
  state: CaptionItemState
  existingText: string
  generatedText: string
  finalText: string
  tags: CaptionTag[]
  error?: string
  written: boolean
  edited: boolean
  elapsedMs?: number
  thumbnailUrl: string
}

export interface CaptionJobItemsResponse {
  jobId: string
  total: number
  offset: number
  limit: number
  items: CaptionJobItem[]
}

export interface CaptionCommitRequest {
  itemIds?: string[]
  conflictPolicy?: CaptionConflictPolicy
  backupExisting?: boolean
}

export type TagEditorRoot = 'train' | 'datasets' | 'workspace'
export type TagEditorItemState = 'all' | 'with' | 'missing' | 'empty' | 'errors' | 'duplicate'
export type TagEditorSort = 'path_asc' | 'path_desc' | 'caption_asc' | 'modified_desc'

export interface TagEditorInspectRequest {
  root: TagEditorRoot
  path: string
  recursive: boolean
  captionExtension: string
  maxImages: number
  initialLimit?: number
}

export interface TagEditorTagCount {
  text: string
  count: number
}

export interface TagEditorDatasetSummary {
  id: string
  revision: string
  root: string
  path: string
  recursive: boolean
  captionExtension: string
  total: number
  withCaption: number
  missing: number
  empty: number
  errors: number
  duplicates: number
  truncated: boolean
  createdAt: string
}

export interface TagEditorDatasetItem {
  id: string
  name: string
  relativePath: string
  width?: number
  height?: number
  captionExists: boolean
  captionText: string
  captionPreviewTruncated: boolean
  sourceTruncated: boolean
  writable: boolean
  error?: string
  errorCode?: string
  duplicateCount: number
  tags: string[]
  thumbnailUrl: string
}

export type TagEditorItem = TagEditorDatasetItem

/** The detail endpoint removes list-preview truncation; source limits are reported separately. */
export type TagEditorDatasetItemDetail = TagEditorDatasetItem
export type TagEditorItemDetail = TagEditorDatasetItemDetail

export interface TagEditorInspectResponse {
  dataset: TagEditorDatasetSummary
  items: TagEditorDatasetItem[]
  commonTags: TagEditorTagCount[]
}

export interface TagEditorItemsResponse {
  datasetId: string
  revision: string
  total: number
  offset: number
  limit: number
  items: TagEditorDatasetItem[]
}

export interface TagEditorItemsQuery {
  offset?: number
  limit?: number
  query?: string
  state?: TagEditorItemState
  sort?: TagEditorSort
}

export interface TagEditorIncludeScope {
  mode: 'include'
  includeIds: string[]
}

export interface TagEditorFilterScope {
  mode: 'filter'
  query: string
  state: TagEditorItemState
  exclusions: string[]
}

export type TagEditorScope = TagEditorIncludeScope | TagEditorFilterScope
export type TagEditorOperationMode = 'tags' | 'text'

export interface TagEditorSetOperation {
  type: 'set'
  text: string
}

export interface TagEditorAddOperation {
  type: 'add'
  mode: TagEditorOperationMode
  values: string[]
  position: 'start' | 'end'
  separator: string
  deduplicate: boolean
}

export interface TagEditorRemoveOperation {
  type: 'remove'
  mode: TagEditorOperationMode
  values: string[]
  matchCase: boolean
  wholeWord: boolean
  separator: string
}

export interface TagEditorReplaceOperation {
  type: 'replace'
  search: string
  replacement: string
  useRegex: boolean
  matchCase: boolean
  wholeWord: boolean
}

export interface TagEditorNormalizeOperation {
  type: 'normalize'
  mode: TagEditorOperationMode
  separator: string
  trim: boolean
  deduplicate: boolean
  sort: 'none' | 'alphabetical' | 'natural'
  caseSensitive: boolean
  replaceUnderscore: boolean
}

export type TagEditorOperation =
  | TagEditorSetOperation
  | TagEditorAddOperation
  | TagEditorRemoveOperation
  | TagEditorReplaceOperation
  | TagEditorNormalizeOperation

export interface TagEditorPreviewRequest {
  revision: string
  scope: TagEditorScope
  operations: TagEditorOperation[]
  sampleLimit?: number
}

export interface TagEditorDiff {
  itemId: string
  name: string
  relativePath: string
  before: string
  after: string
  beforeTruncated: boolean
  afterTruncated: boolean
}

export interface TagEditorPreviewIssue {
  itemId: string
  name: string
  relativePath: string
  error: string
}

export type TagEditorChangeState =
  | 'previewed'
  | 'queued'
  | 'applying'
  | 'completed'
  | 'partial'
  | 'failed'
  | 'rolling_back'
  | 'rolled_back'
  | 'rollback_partial'
  | 'interrupted'

export interface TagEditorChangeSetSummary {
  id: string
  datasetId: string
  datasetPath: string
  revision: string
  resultRevision?: string
  state: TagEditorChangeState
  message: string
  matched: number
  changed: number
  unchanged: number
  conflicts: number
  failed: number
  applied: number
  rolledBack: number
  rollbackConflicts: number
  backupExisting: boolean
  canRollback: boolean
  createdAt: string
  startedAt?: string
  endedAt?: string
}

export interface TagEditorPreviewResponse extends TagEditorChangeSetSummary {
  diffs: TagEditorDiff[]
  issues: TagEditorPreviewIssue[]
}

export interface TagEditorApplyRequest {
  changeSetId: string
  revision: string
  backupExisting: boolean
}

export interface TagEditorChangeSetListResponse {
  changes: TagEditorChangeSetSummary[]
}

export interface TagEditorTagSuggestionsResponse {
  datasetId: string
  query: string
  suggestions: TagEditorTagCount[]
}

export type TagEditorChangeResultState =
  | 'applied'
  | 'conflict'
  | 'failed'
  | 'rolled_back'
  | 'rollback_conflict'

export interface TagEditorChangeResult {
  itemId: string
  relativePath: string
  state: TagEditorChangeResultState
  error?: string
}

export interface TagEditorChangeResultsResponse {
  changeSetId: string
  total: number
  offset: number
  limit: number
  items: TagEditorChangeResult[]
}
