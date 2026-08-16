import { defineStore } from 'pinia'

import { apiClient } from '@/api/client'
import type { CompileResult, ParamDefinition, SampleDraft, TrainDraft } from '@/api/types'

const DRAFT_STORAGE_KEY = 'ls-v2-drafts'
const DRAFT_STORAGE_VERSION = 3
const COMPATIBLE_DRAFT_VERSIONS = new Set([1, 2, DRAFT_STORAGE_VERSION])

interface DatasetDraft {
  mode: string
  root: string
  captionExtension: string
  resolution: [number, number]
  batchSize: number
  numRepeats: number
  enableBucket: boolean
  minBucketReso: number
  maxBucketReso: number
  bucketResoSteps: number
  bucketNoUpscale: boolean
  shuffleCaption: boolean
  keepTokens: number
}

function emptyDataset(defaults: Record<string, unknown> = {}): DatasetDraft {
  const baseline: DatasetDraft = {
    mode: 'simple',
    root: '',
    captionExtension: '.txt',
    resolution: [1024, 1024],
    batchSize: 1,
    numRepeats: 1,
    enableBucket: true,
    minBucketReso: 256,
    maxBucketReso: 2048,
    bucketResoSteps: 64,
    bucketNoUpscale: true,
    shuffleCaption: false,
    keepTokens: 0,
  }
  const rawResolution = defaults.resolution
  const resolution: [number, number] =
    Array.isArray(rawResolution) && rawResolution.length === 2
      ? [Number(rawResolution[0]), Number(rawResolution[1])]
      : baseline.resolution

  return {
    ...baseline,
    ...defaults,
    mode: 'simple',
    root: '',
    resolution,
  } as DatasetDraft
}

function emptySample(resolution: [number, number] = [1024, 1024]): SampleDraft {
  return {
    enabled: false,
    everyNEpochs: 1,
    prompts: [{ prompt: '', width: resolution[0], height: resolution[1], steps: 20, seed: 1337, cfgScale: 1 }],
  }
}

type StoredSampleDraft = Omit<SampleDraft, 'everyNEpochs' | 'everyNSteps'> & {
  everyNEpochs?: number | null
  everyNSteps?: number | null
}

interface StoredDraft {
  version: number
  manifestHash?: string
  savedAt: string
  name: string
  modelAssets: Record<string, unknown>
  params: Record<string, unknown>
  dataset: DatasetDraft
  runtime: TrainDraft['runtime']
  sample: StoredSampleDraft
}

function readStoredDrafts(): Record<string, StoredDraft> {
  try {
    const parsed = JSON.parse(localStorage.getItem(DRAFT_STORAGE_KEY) || '{}') as unknown
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed)
      ? (parsed as Record<string, StoredDraft>)
      : {}
  } catch {
    return {}
  }
}

function cloneRecord(value: Record<string, unknown>) {
  return JSON.parse(JSON.stringify(value)) as Record<string, unknown>
}

function cloneParamValue(value: unknown): unknown {
  if (value === undefined || value === null || typeof value !== 'object') return value
  return JSON.parse(JSON.stringify(value)) as unknown
}

function serializeSample(value: SampleDraft): StoredSampleDraft {
  return {
    ...(JSON.parse(JSON.stringify(value)) as StoredSampleDraft),
    // JSON drops `undefined`. Persist both schedule keys explicitly so a
    // step-based schedule cannot regain the product epoch default on reload.
    everyNEpochs: value.everyNEpochs ?? null,
    everyNSteps: value.everyNSteps ?? null,
  }
}

function restoreSample(
  value: StoredSampleDraft | undefined,
  resolution: [number, number] = [1024, 1024],
): SampleDraft {
  const baseline = emptySample(resolution)
  if (!value || typeof value !== 'object') return baseline

  const restored = {
    ...baseline,
    ...(JSON.parse(JSON.stringify(value)) as StoredSampleDraft),
    prompts: Array.isArray(value.prompts)
      ? JSON.parse(JSON.stringify(value.prompts)) as SampleDraft['prompts']
      : baseline.prompts,
  } as SampleDraft
  const hasEpochSchedule = hasOwn(value as Record<string, unknown>, 'everyNEpochs')
  const hasStepSchedule = hasOwn(value as Record<string, unknown>, 'everyNSteps')

  if (!hasEpochSchedule && !hasStepSchedule) return restored

  const everyNEpochs = typeof value.everyNEpochs === 'number' ? value.everyNEpochs : undefined
  const everyNSteps = typeof value.everyNSteps === 'number' ? value.everyNSteps : undefined

  // Pre-v3 snapshots could contain the implicit epoch default together with
  // an explicit step interval. The step interval is the user's stronger
  // signal, so migrate that invalid pair to a step-only schedule.
  if (everyNSteps !== undefined) {
    restored.everyNEpochs = undefined
    restored.everyNSteps = everyNSteps
  } else {
    restored.everyNEpochs = everyNEpochs
    restored.everyNSteps = undefined
  }
  return restored
}

function hasOwn(record: Record<string, unknown>, name: string) {
  return Object.prototype.hasOwnProperty.call(record, name)
}

function isUnsetValue(value: unknown) {
  if (value === undefined || value === null) return true
  if (typeof value === 'string') return value.trim() === ''
  if (Array.isArray(value)) return value.length === 0
  if (typeof value === 'object') return Object.keys(value).length === 0
  return false
}

function hasEffectiveDefault(param: ParamDefinition) {
  return param.effectiveDefault !== undefined && param.effectiveDefault !== null
}

function reconcileParamRecords(
  definitions: ParamDefinition[],
  savedModelAssets: Record<string, unknown>,
  savedParams: Record<string, unknown>,
) {
  const modelAssets: Record<string, unknown> = {}
  const params: Record<string, unknown> = {}

  for (const param of definitions) {
    if (param.hidden || param.sensitive) continue

    const target = param.group === 'model' ? modelAssets : params
    const preferred = param.group === 'model' ? savedModelAssets : savedParams
    const previousGroup = param.group === 'model' ? savedParams : savedModelAssets
    const source = hasOwn(preferred, param.name)
      ? preferred
      : hasOwn(previousGroup, param.name)
        ? previousGroup
        : null

    if (source) {
      const savedValue = source[param.name]
      if (savedValue === null && hasEffectiveDefault(param)) {
        // `null` is an explicit tombstone: keep the product default out of
        // the compiled config and let the underlying parser use its default.
        target[param.name] = null
        continue
      }
      const isMaterializedArgparseDefault =
        !hasEffectiveDefault(param) &&
        param.default !== undefined &&
        valuesEqual(savedValue, param.default)
      if (!isUnsetValue(savedValue) && !isMaterializedArgparseDefault) {
        target[param.name] = cloneParamValue(savedValue)
        continue
      }
    }

    if (hasEffectiveDefault(param)) {
      target[param.name] = cloneParamValue(param.effectiveDefault)
    }
  }

  return { modelAssets, params }
}

function valuesEqual(left: unknown, right: unknown) {
  return JSON.stringify(left) === JSON.stringify(right)
}

function collectStoredOverrides(
  definitions: ParamDefinition[],
  source: Record<string, unknown>,
  group: 'model' | 'params',
) {
  const overrides: Record<string, unknown> = {}
  for (const param of definitions) {
    const belongsToGroup = group === 'model' ? param.group === 'model' : param.group !== 'model'
    if (!belongsToGroup || param.sensitive || !hasOwn(source, param.name)) continue

    const value = source[param.name]
    const baseline = hasEffectiveDefault(param) ? param.effectiveDefault : param.default
    if (value !== null && baseline !== undefined && valuesEqual(value, baseline)) continue
    if (value === null && !hasEffectiveDefault(param)) continue
    overrides[param.name] = cloneParamValue(value)
  }
  return overrides
}

function migrateLegacySnapshot(
  definitions: ParamDefinition[],
  savedModelAssets: Record<string, unknown>,
  savedParams: Record<string, unknown>,
) {
  const modelAssets: Record<string, unknown> = {}
  const params: Record<string, unknown> = {}

  for (const param of definitions) {
    if (param.hidden || param.sensitive || hasEffectiveDefault(param)) continue

    const target = param.group === 'model' ? modelAssets : params
    const preferred = param.group === 'model' ? savedModelAssets : savedParams
    const previousGroup = param.group === 'model' ? savedParams : savedModelAssets
    const source = hasOwn(preferred, param.name)
      ? preferred
      : hasOwn(previousGroup, param.name)
        ? previousGroup
        : null
    if (!source) continue

    const savedValue = source[param.name]
    if (isUnsetValue(savedValue)) continue
    if (param.default !== undefined && valuesEqual(savedValue, param.default)) continue
    target[param.name] = cloneParamValue(savedValue)
  }

  return { modelAssets, params }
}

function storedParamSources(
  saved: StoredDraft,
  definitions: ParamDefinition[],
  manifestHash: string,
) {
  const savedModelAssets = cloneRecord(saved.modelAssets || {})
  const savedParams = cloneRecord(saved.params || {})
  const catalogChanged =
    saved.version !== DRAFT_STORAGE_VERSION &&
    !!manifestHash &&
    saved.manifestHash !== manifestHash

  if (!catalogChanged) {
    return { modelAssets: savedModelAssets, params: savedParams }
  }

  // Versions 1–2 stored a fully materialized snapshot. Once the catalog
  // changes, values belonging to an effectiveDefault are ambiguous: treating
  // them as overrides would pin the old product defaults forever. Preserve
  // only unambiguous, non-default user values and apply the new catalog.
  return migrateLegacySnapshot(definitions, savedModelAssets, savedParams)
}

export const useDraftStore = defineStore('draft', {
  state: () => ({
    name: 'aki_lora',
    modelAssets: {} as Record<string, unknown>,
    params: {} as Record<string, unknown>,
    dataset: emptyDataset(),
    runtime: {
      gpuIds: [] as string[],
      numCpuThreadsPerProcess: 8,
    },
    sample: emptySample(),
    compiling: false,
    compileResult: null as CompileResult | null,
    compileError: '',
    compiledSignature: '',
    manifestHash: '',
    hydratedTrainerId: '',
    lastSavedAt: '',
    storageError: '',
    restoredFromStorage: false,
  }),
  actions: {
    resetForTrainer(
      params: ParamDefinition[],
      trainerId = '',
      manifestHash = '',
      restoreSaved = true,
      datasetDefaults: Record<string, unknown> = {},
    ) {
      this.compileResult = null
      this.compileError = ''
      this.compiledSignature = ''
      this.storageError = ''
      this.restoredFromStorage = false

      if (trainerId && restoreSaved) {
        const saved = readStoredDrafts()[trainerId]
        if (saved && COMPATIBLE_DRAFT_VERSIONS.has(saved.version)) {
          const sources = storedParamSources(saved, params, manifestHash)
          const reconciled = reconcileParamRecords(
            params,
            sources.modelAssets,
            sources.params,
          )
          this.name = typeof saved.name === 'string' ? saved.name : 'aki_lora'
          this.modelAssets = reconciled.modelAssets
          this.params = reconciled.params
          this.dataset = {
            ...emptyDataset(datasetDefaults),
            ...(saved.dataset || {}),
            resolution:
              Array.isArray(saved.dataset?.resolution) && saved.dataset.resolution.length === 2
                ? [...saved.dataset.resolution]
                : emptyDataset(datasetDefaults).resolution,
          }
          this.runtime = {
            gpuIds: Array.isArray(saved.runtime?.gpuIds) ? [...saved.runtime.gpuIds] : [],
            numCpuThreadsPerProcess: Number(saved.runtime?.numCpuThreadsPerProcess) || 8,
          }
          this.sample = restoreSample(saved.sample, this.dataset.resolution)
          this.manifestHash = manifestHash || saved.manifestHash || ''
          this.hydratedTrainerId = trainerId
          this.lastSavedAt = saved.savedAt || ''
          this.restoredFromStorage = true
          return
        }
      }

      this.name = 'aki_lora'
      this.modelAssets = {}
      this.params = {}
      this.dataset = emptyDataset(datasetDefaults)
      this.runtime = { gpuIds: [], numCpuThreadsPerProcess: 8 }
      this.sample = emptySample(this.dataset.resolution)
      this.manifestHash = manifestHash
      this.hydratedTrainerId = trainerId
      this.lastSavedAt = ''

      const reconciled = reconcileParamRecords(params, {}, {})
      this.modelAssets = reconciled.modelAssets
      this.params = reconciled.params
    },

    resetToDefaults(
      params: ParamDefinition[],
      trainerId: string,
      manifestHash = '',
      datasetDefaults: Record<string, unknown> = {},
    ) {
      if (trainerId) {
        try {
          const drafts = readStoredDrafts()
          delete drafts[trainerId]
          localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify(drafts))
        } catch (error) {
          this.storageError = error instanceof Error ? error.message : String(error)
        }
      }
      this.resetForTrainer(params, trainerId, manifestHash, false, datasetDefaults)
    },

    persistForTrainer(trainerId: string, definitions: ParamDefinition[] = []) {
      if (!trainerId) return false
      if (trainerId !== this.hydratedTrainerId) {
        this.storageError = '训练器参数仍在加载，草稿尚未保存'
        return false
      }
      if (!definitions.length) {
        this.storageError = '完整参数目录尚未加载，草稿尚未保存'
        return false
      }
      try {
        const savedAt = new Date().toISOString()
        const drafts = readStoredDrafts()
        drafts[trainerId] = {
          version: DRAFT_STORAGE_VERSION,
          manifestHash: this.manifestHash,
          savedAt,
          name: this.name,
          modelAssets: collectStoredOverrides(definitions, this.modelAssets, 'model'),
          params: collectStoredOverrides(definitions, this.params, 'params'),
          dataset: JSON.parse(JSON.stringify(this.dataset)) as DatasetDraft,
          runtime: {
            gpuIds: [...this.runtime.gpuIds],
            numCpuThreadsPerProcess: this.runtime.numCpuThreadsPerProcess,
          },
          sample: serializeSample(this.sample),
        }
        localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify(drafts))
        this.lastSavedAt = savedAt
        this.storageError = ''
        return true
      } catch (error) {
        this.storageError = error instanceof Error ? error.message : String(error)
        return false
      }
    },

    reconcileForCatalog(params: ParamDefinition[], manifestHash = '', trainerId = '') {
      if (!params.length) return
      if (trainerId && trainerId !== this.hydratedTrainerId) return

      const nextManifestHash = manifestHash || this.manifestHash
      let sourceModelAssets = this.modelAssets
      let sourceParams = this.params
      if (trainerId && nextManifestHash !== this.manifestHash) {
        const saved = readStoredDrafts()[trainerId]
        if (saved && COMPATIBLE_DRAFT_VERSIONS.has(saved.version)) {
          // Version 3 stores overrides only. Legacy snapshots use the
          // conservative migration above when their catalog changed.
          const sources = storedParamSources(saved, params, nextManifestHash)
          sourceModelAssets = sources.modelAssets
          sourceParams = sources.params
        }
      }
      const reconciled = reconcileParamRecords(params, sourceModelAssets, sourceParams)
      const changed =
        nextManifestHash !== this.manifestHash ||
        !valuesEqual(reconciled.modelAssets, this.modelAssets) ||
        !valuesEqual(reconciled.params, this.params)

      this.modelAssets = reconciled.modelAssets
      this.params = reconciled.params
      this.manifestHash = nextManifestHash

      if (changed) {
        this.compileResult = null
        this.compileError = ''
        this.compiledSignature = ''
      }
    },

    getValue(param: ParamDefinition) {
      return param.group === 'model' ? this.modelAssets[param.name] : this.params[param.name]
    },

    unsetValue(param: ParamDefinition) {
      if (param.group === 'model') {
        delete this.modelAssets[param.name]
      } else {
        delete this.params[param.name]
      }
    },

    resetValue(param: ParamDefinition) {
      if (!hasEffectiveDefault(param) || isUnsetValue(param.effectiveDefault)) {
        this.unsetValue(param)
        return
      }

      const target = param.group === 'model' ? this.modelAssets : this.params
      target[param.name] = cloneParamValue(param.effectiveDefault)
    },

    setValue(param: ParamDefinition, value: unknown) {
      const target = param.group === 'model' ? this.modelAssets : this.params
      if (isUnsetValue(value)) {
        if (hasEffectiveDefault(param)) {
          target[param.name] = null
        } else {
          this.unsetValue(param)
        }
        return
      }

      target[param.name] = value
    },

    isValueModified(param: ParamDefinition) {
      const target = param.group === 'model' ? this.modelAssets : this.params
      if (!hasOwn(target, param.name)) return false
      const current = this.getValue(param)

      const baseline = hasEffectiveDefault(param) ? param.effectiveDefault : param.default
      return !valuesEqual(current, baseline)
    },

    buildDraft(trainerId: string): TrainDraft {
      return {
        trainerId,
        name: this.name.trim(),
        modelAssets: this.modelAssets,
        dataset: this.dataset,
        params: this.params,
        runtime: this.runtime,
        sample: this.sample,
      }
    },

    signature(trainerId: string) {
      return JSON.stringify({
        manifestHash: this.manifestHash,
        draft: this.buildDraft(trainerId),
      })
    },

    async compile(
      trainerId: string,
      options: { validatePaths?: boolean } = {},
    ): Promise<CompileResult | null> {
      if (!trainerId || trainerId !== this.hydratedTrainerId) {
        this.compileError = '训练器参数仍在加载，请稍后重试'
        return null
      }
      this.compiling = true
      this.compileError = ''
      this.compileResult = null
      this.compiledSignature = ''
      try {
        const signature = this.signature(trainerId)
        this.compileResult = await apiClient.compileDraft(this.buildDraft(trainerId), {
          persist: false,
          validatePaths: options.validatePaths ?? false,
        })
        this.compiledSignature = signature
        return this.compileResult
      } catch (error) {
        this.compileError = error instanceof Error ? error.message : String(error)
        return null
      } finally {
        this.compiling = false
      }
    },
  },
})
