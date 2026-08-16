import { computed, ref, watch, type Ref } from 'vue'

import type { JobMetricPoint, JobMetricSeries } from '@/api/types'

export type MetricGroupId = 'loss' | 'lr' | 'norm' | 'other'
export type DerivedCurveOperation = 'ema' | 'sma' | 'difference' | 'ratio'

export interface DerivedCurveDefinition {
  id: string
  label: string
  operation: DerivedCurveOperation
  sourceA: string
  sourceB?: string
  window?: number
  enabled: boolean
}

export interface DerivedCurveDraft {
  label: string
  operation: DerivedCurveOperation
  sourceA: string
  sourceB?: string
  window?: number
}

export interface DisplayMetricSeries extends JobMetricSeries {
  id: string
  label: string
  group: MetricGroupId
  derived: boolean
}

export const METRIC_GROUPS: Array<{ id: MetricGroupId; label: string }> = [
  { id: 'loss', label: '损失' },
  { id: 'lr', label: '学习率' },
  { id: 'norm', label: '范数' },
  { id: 'other', label: '其他' },
]

const OPERATIONS = new Set<DerivedCurveOperation>(['ema', 'sma', 'difference', 'ratio'])
const MAX_WINDOW = 500

export function metricGroup(tag: string): MetricGroupId {
  const normalized = tag.trim().toLocaleLowerCase()
  if (normalized.includes('loss') || normalized === 'avr_loss') return 'loss'
  if (
    normalized === 'lr' ||
    normalized.includes('learning_rate') ||
    normalized.includes('learning-rate') ||
    /(^|[/_.-])lr([/_.-]|$)/u.test(normalized)
  ) {
    return 'lr'
  }
  if (normalized.includes('norm')) return 'norm'
  return 'other'
}

function movingAverage(points: JobMetricPoint[], window: number): JobMetricPoint[] {
  const result: JobMetricPoint[] = []
  let sum = 0
  const values: number[] = []
  for (const point of points) {
    values.push(point.value)
    sum += point.value
    if (values.length > window) sum -= values.shift() || 0
    result.push({ ...point, value: sum / values.length })
  }
  return result
}

function exponentialAverage(points: JobMetricPoint[], window: number): JobMetricPoint[] {
  const alpha = 2 / (window + 1)
  let average: number | undefined
  return points.map((point) => {
    average = average === undefined ? point.value : alpha * point.value + (1 - alpha) * average
    return { ...point, value: average }
  })
}

function combineSeries(
  left: JobMetricPoint[],
  right: JobMetricPoint[],
  operation: 'difference' | 'ratio',
): JobMetricPoint[] {
  const rightByStep = new Map<number, JobMetricPoint>()
  for (const point of right) rightByStep.set(point.step, point)

  const result: JobMetricPoint[] = []
  for (const point of left) {
    const counterpart = rightByStep.get(point.step)
    if (!counterpart) continue
    if (operation === 'ratio' && counterpart.value === 0) continue
    const value = operation === 'difference'
      ? point.value - counterpart.value
      : point.value / counterpart.value
    if (Number.isFinite(value)) result.push({ ...point, value })
  }
  return result
}

function normalizedDefinition(value: unknown): DerivedCurveDefinition | null {
  if (!value || typeof value !== 'object') return null
  const definition = value as Partial<DerivedCurveDefinition>
  if (
    typeof definition.id !== 'string' ||
    typeof definition.label !== 'string' ||
    typeof definition.sourceA !== 'string' ||
    !OPERATIONS.has(definition.operation as DerivedCurveOperation)
  ) {
    return null
  }
  const operation = definition.operation as DerivedCurveOperation
  const needsSourceB = operation === 'difference' || operation === 'ratio'
  if (needsSourceB && typeof definition.sourceB !== 'string') return null
  return {
    id: definition.id.slice(0, 80),
    label: definition.label.trim().slice(0, 64),
    operation,
    sourceA: definition.sourceA,
    sourceB: needsSourceB ? definition.sourceB : undefined,
    window:
      operation === 'ema' || operation === 'sma'
        ? Math.min(MAX_WINDOW, Math.max(2, Math.round(definition.window || 20)))
        : undefined,
    enabled: definition.enabled !== false,
  }
}

function storageKey(trainerId: string, suffix: string) {
  return `mikazuki.metrics.${suffix}.v1:${trainerId || 'default'}`
}

function readJsonStorage(key: string): unknown {
  if (typeof window === 'undefined') return null
  try {
    const value = window.localStorage.getItem(key)
    return value ? JSON.parse(value) as unknown : null
  } catch {
    return null
  }
}

function writeJsonStorage(key: string, value: unknown) {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // Storage is an enhancement; private mode or quota limits must not break charts.
  }
}

function newCurveId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  return `curve_${Date.now()}_${Math.random().toString(16).slice(2)}`
}

export function useMetricCurves(series: Ref<JobMetricSeries[]>, trainerId: Ref<string>) {
  const activeGroup = ref<MetricGroupId>('loss')
  const selectedTags = ref<string[]>([])
  const definitions = ref<DerivedCurveDefinition[]>([])
  let loadingPreferences = false

  const rawByTag = computed(() => new Map(series.value.map((item) => [item.tag, item])))
  const groupedSeries = computed(() => {
    const groups: Record<MetricGroupId, JobMetricSeries[]> = {
      loss: [],
      lr: [],
      norm: [],
      other: [],
    }
    for (const item of series.value) groups[metricGroup(item.tag)].push(item)
    return groups
  })

  const groupCounts = computed<Record<MetricGroupId, number>>(() => ({
    loss: groupedSeries.value.loss.length,
    lr: groupedSeries.value.lr.length,
    norm: groupedSeries.value.norm.length,
    other: groupedSeries.value.other.length,
  }))

  const availableTags = computed(() => groupedSeries.value[activeGroup.value].map((item) => item.tag))

  const derivedSeries = computed<DisplayMetricSeries[]>(() => {
    const output: DisplayMetricSeries[] = []
    for (const definition of definitions.value) {
      if (!definition.enabled) continue
      const sourceA = rawByTag.value.get(definition.sourceA)
      if (!sourceA) continue

      let points: JobMetricPoint[] = []
      if (definition.operation === 'ema') {
        points = exponentialAverage(sourceA.points, definition.window || 20)
      } else if (definition.operation === 'sma') {
        points = movingAverage(sourceA.points, definition.window || 20)
      } else {
        const sourceB = definition.sourceB ? rawByTag.value.get(definition.sourceB) : undefined
        if (!sourceB) continue
        points = combineSeries(sourceA.points, sourceB.points, definition.operation)
      }

      output.push({
        id: `derived:${definition.id}`,
        tag: `derived/${definition.id}`,
        label: definition.label,
        group: metricGroup(definition.sourceA),
        derived: true,
        points,
      })
    }
    return output
  })

  const chartSeries = computed<DisplayMetricSeries[]>(() => {
    const raw: DisplayMetricSeries[] = groupedSeries.value[activeGroup.value]
      .filter((item) => selectedTags.value.includes(item.tag))
      .map((item) => ({
        ...item,
        id: `raw:${item.tag}`,
        label: item.tag,
        group: activeGroup.value,
        derived: false,
      }))
    const derived = derivedSeries.value.filter((item) => item.group === activeGroup.value)
    return [...raw, ...derived]
  })

  function chooseDefaults(group = activeGroup.value) {
    const tags = groupedSeries.value[group].map((item) => item.tag)
    if (tags.length === 0) return
    const alreadySelected = tags.some((tag) => selectedTags.value.includes(tag))
    if (alreadySelected) return

    const preferred = tags
      .filter((tag) => /current|average|avr|epoch|unet|textencoder/iu.test(tag))
      .slice(0, 3)
    const next = preferred.length > 0 ? preferred : tags.slice(0, 3)
    selectedTags.value = [...new Set([...selectedTags.value, ...next])]
  }

  function selectGroup(group: MetricGroupId) {
    activeGroup.value = group
    chooseDefaults(group)
  }

  function validateDraft(draft: DerivedCurveDraft): string {
    if (!draft.label.trim()) return '请填写曲线名称。'
    if (!rawByTag.value.has(draft.sourceA)) return '请选择有效的主指标。'
    if (draft.operation === 'ema' || draft.operation === 'sma') {
      const window = Math.round(draft.window || 0)
      if (window < 2 || window > MAX_WINDOW) return `窗口必须在 2 到 ${MAX_WINDOW} 之间。`
    } else {
      if (!draft.sourceB || !rawByTag.value.has(draft.sourceB)) return '请选择用于计算的第二个指标。'
      if (draft.sourceA === draft.sourceB) return '两个来源指标不能相同。'
    }
    return ''
  }

  function addDefinition(draft: DerivedCurveDraft): string {
    const issue = validateDraft(draft)
    if (issue) return issue
    const smoothed = draft.operation === 'ema' || draft.operation === 'sma'
    definitions.value.push({
      id: newCurveId(),
      label: draft.label.trim().slice(0, 64),
      operation: draft.operation,
      sourceA: draft.sourceA,
      sourceB: smoothed ? undefined : draft.sourceB,
      window: smoothed ? Math.min(MAX_WINDOW, Math.max(2, Math.round(draft.window || 20))) : undefined,
      enabled: true,
    })
    return ''
  }

  function removeDefinition(id: string) {
    definitions.value = definitions.value.filter((definition) => definition.id !== id)
  }

  function loadPreferences() {
    loadingPreferences = true
    const storedDefinitions = readJsonStorage(storageKey(trainerId.value, 'curves'))
    definitions.value = Array.isArray(storedDefinitions)
      ? storedDefinitions.map(normalizedDefinition).filter((item): item is DerivedCurveDefinition => item !== null)
      : []
    const storedSelection = readJsonStorage(storageKey(trainerId.value, 'selection'))
    selectedTags.value = Array.isArray(storedSelection)
      ? storedSelection.filter((tag): tag is string => typeof tag === 'string')
      : []
    loadingPreferences = false
    chooseDefaults()
  }

  watch(trainerId, loadPreferences, { immediate: true })
  watch(
    definitions,
    (value) => {
      if (!loadingPreferences) writeJsonStorage(storageKey(trainerId.value, 'curves'), value)
    },
    { deep: true },
  )
  watch(
    selectedTags,
    (value) => {
      if (!loadingPreferences) writeJsonStorage(storageKey(trainerId.value, 'selection'), value)
    },
    { deep: true },
  )
  watch(series, () => {
    const groups = METRIC_GROUPS.filter((group) => groupCounts.value[group.id] > 0)
    if (groupCounts.value[activeGroup.value] === 0 && groups.length > 0) activeGroup.value = groups[0].id
    chooseDefaults()
  }, { deep: true, immediate: true })

  return {
    activeGroup,
    selectedTags,
    definitions,
    groupedSeries,
    groupCounts,
    availableTags,
    chartSeries,
    selectGroup,
    validateDraft,
    addDefinition,
    removeDefinition,
  }
}
