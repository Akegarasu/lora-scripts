<script setup lang="ts">
import { computed, ref } from 'vue'
import { Delete, Plus, RefreshRight } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { storeToRefs } from 'pinia'

import { useMetricsStore } from '@/stores/metrics'

import MetricLineChart from './MetricLineChart.vue'
import {
  METRIC_GROUPS,
  metricGroup,
  useMetricCurves,
  type DerivedCurveDraft,
  type DerivedCurveOperation,
} from './useMetricCurves'

const props = defineProps<{
  trainerId: string
}>()

const emit = defineEmits<{
  showLog: []
}>()

const metrics = useMetricsStore()
const {
  series,
  status,
  loading,
  error,
  lastEventAt,
  pointCount,
  hasMetrics,
  available,
  parseErrors,
  terminal,
} = storeToRefs(metrics)

const trainerIdRef = computed(() => props.trainerId)
const {
  activeGroup,
  selectedTags,
  definitions,
  groupCounts,
  availableTags,
  chartSeries,
  selectGroup,
  addDefinition,
  removeDefinition,
} = useMetricCurves(series, trainerIdRef)

const dialogVisible = ref(false)
const dialogError = ref('')
const curveDraft = ref<DerivedCurveDraft>({
  label: '',
  operation: 'ema',
  sourceA: '',
  window: 20,
})

const operationOptions: Array<{ value: DerivedCurveOperation; label: string; description: string }> = [
  { value: 'ema', label: 'EMA', description: '指数移动平均，更快跟随近期变化' },
  { value: 'sma', label: 'SMA', description: '简单移动平均，平滑短期噪声' },
  { value: 'difference', label: '差值', description: '主指标减去第二个指标' },
  { value: 'ratio', label: '比值', description: '主指标除以第二个指标，自动跳过除数为 0 的点' },
]

const currentSelection = computed<string[]>({
  get: () => selectedTags.value.filter((tag) => availableTags.value.includes(tag)),
  set: (value) => {
    const current = new Set(availableTags.value)
    selectedTags.value = [
      ...selectedTags.value.filter((tag) => !current.has(tag)),
      ...value,
    ]
  },
})

const allTags = computed(() => series.value.map((item) => item.tag).sort((left, right) => left.localeCompare(right)))
const currentDefinitions = computed(() =>
  definitions.value.filter((definition) => metricGroup(definition.sourceA) === activeGroup.value),
)
const needsWindow = computed(() => curveDraft.value.operation === 'ema' || curveDraft.value.operation === 'sma')
const needsSecondSource = computed(() => !needsWindow.value)
const lastEventLabel = computed(() => {
  if (!lastEventAt.value) return ''
  const timestamp = new Date(lastEventAt.value)
  if (Number.isNaN(timestamp.getTime())) return ''
  return timestamp.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  })
})

const parseErrorMessage = computed(() => {
  if (parseErrors.value.length === 0) return ''
  return `指标文件解析失败：${parseErrors.value.join('；')}`
})

const noticeMessage = computed(() => parseErrorMessage.value || error.value)

const emptyDescription = computed(() => {
  if (parseErrorMessage.value) return parseErrorMessage.value
  if (error.value) return error.value
  if (available.value === false) {
    return terminal.value ? '任务已结束，但没有生成可读取的指标文件' : '等待训练器创建事件文件'
  }
  return terminal.value ? '任务没有记录可绘制的指标' : '当前还没有可绘制的指标'
})

const statusLabel = computed(() => {
  if (parseErrorMessage.value) return '指标文件解析失败'
  if (status.value === 'loading') return '正在读取指标'
  if (status.value === 'connecting') return '正在连接实时指标'
  if (status.value === 'disconnected') return '实时连接已中断'
  if (status.value === 'ended') return '指标记录已结束'
  if (status.value === 'unavailable') return '没有指标记录'
  if (available.value === false && !terminal.value) return '等待事件文件'
  if (status.value === 'live') return '实时指标'
  return '等待指标'
})

function suggestedLabel(operation: DerivedCurveOperation, source: string) {
  const suffix: Record<DerivedCurveOperation, string> = {
    ema: 'EMA',
    sma: 'SMA',
    difference: '差值',
    ratio: '比值',
  }
  return source ? `${source} · ${suffix[operation]}` : suffix[operation]
}

function openCurveDialog() {
  const sourceA = availableTags.value[0] || allTags.value[0] || ''
  curveDraft.value = {
    label: suggestedLabel('ema', sourceA),
    operation: 'ema',
    sourceA,
    window: 20,
  }
  dialogError.value = ''
  dialogVisible.value = true
}

function onOperationChange(operation: DerivedCurveOperation) {
  curveDraft.value.label = suggestedLabel(operation, curveDraft.value.sourceA)
  curveDraft.value.sourceB = undefined
  curveDraft.value.window = operation === 'ema' || operation === 'sma' ? 20 : undefined
  dialogError.value = ''
}

function onSourceChange(source: string) {
  curveDraft.value.label = suggestedLabel(curveDraft.value.operation, source)
  dialogError.value = ''
}

function saveCurve() {
  const issue = addDefinition(curveDraft.value)
  if (issue) {
    dialogError.value = issue
    return
  }
  dialogVisible.value = false
  ElMessage.success('自定义曲线已添加')
}
</script>

<template>
  <div class="metrics-panel">
    <div class="metrics-toolbar">
      <div class="metric-status" aria-live="polite">
        <span
          class="status-dot"
          :class="{
            live: status === 'live',
            warning: status === 'disconnected',
            quiet: status === 'ended' || status === 'unavailable',
          }"
          aria-hidden="true"
        />
        <div>
          <strong>{{ statusLabel }}</strong>
          <span v-if="hasMetrics">
            {{ series.length }} 项 · {{ pointCount.toLocaleString('zh-CN') }} 个点
            <template v-if="lastEventLabel"> · {{ lastEventLabel }}</template>
          </span>
          <span v-else>训练器上报 scalar 后会自动出现</span>
        </div>
      </div>

      <div class="metric-actions">
        <el-button
          size="small"
          text
          :icon="RefreshRight"
          :loading="loading"
          @click="metrics.reconnect()"
        >
          重新读取
        </el-button>
        <el-button
          size="small"
          :icon="Plus"
          :disabled="allTags.length === 0"
          @click="openCurveDialog"
        >
          添加曲线
        </el-button>
      </div>
    </div>

    <template v-if="hasMetrics">
      <div class="metric-group-tabs" role="tablist" aria-label="指标分组">
        <button
          v-for="group in METRIC_GROUPS"
          :key="group.id"
          type="button"
          role="tab"
          :class="{ active: activeGroup === group.id }"
          :aria-selected="activeGroup === group.id"
          :disabled="groupCounts[group.id] === 0"
          @click="selectGroup(group.id)"
        >
          <span>{{ group.label }}</span>
          <small>{{ groupCounts[group.id] }}</small>
        </button>
      </div>

      <div class="metric-controls">
        <el-select
          v-model="currentSelection"
          class="metric-picker"
          multiple
          collapse-tags
          collapse-tags-tooltip
          clearable
          placeholder="选择原始指标"
          aria-label="选择要显示的原始指标"
        >
          <el-option v-for="tag in availableTags" :key="tag" :label="tag" :value="tag" />
        </el-select>
      </div>

      <div v-if="noticeMessage" class="metric-notice" role="status">
        <span>{{ noticeMessage }}</span>
        <button type="button" @click="metrics.reconnect()">重新连接</button>
      </div>

      <div v-if="chartSeries.length" class="metric-chart-shell">
        <MetricLineChart :series="chartSeries" :group="activeGroup" />
      </div>
      <div v-else class="metric-group-empty">
        <strong>当前分组没有选中的曲线</strong>
        <span>从上方列表选择原始指标，或添加一条自定义曲线。</span>
      </div>

      <div v-if="currentDefinitions.length" class="custom-curve-list" aria-label="当前分组的自定义曲线">
        <span class="custom-curve-title">自定义</span>
        <div v-for="definition in currentDefinitions" :key="definition.id" class="custom-curve-item">
          <el-switch v-model="definition.enabled" size="small" :aria-label="`显示 ${definition.label}`" />
          <span :title="definition.label">{{ definition.label }}</span>
          <el-button
            text
            circle
            size="small"
            :icon="Delete"
            :aria-label="`删除 ${definition.label}`"
            @click="removeDefinition(definition.id)"
          />
        </div>
      </div>
    </template>

    <div v-else-if="loading" class="metric-loading" aria-label="正在加载指标">
      <el-skeleton :rows="6" animated />
    </div>

    <div v-else class="metric-empty">
      <el-empty :image-size="72" :description="emptyDescription">
        <div class="empty-actions">
          <el-button size="small" :icon="RefreshRight" @click="metrics.reconnect()">重试</el-button>
          <el-button size="small" text @click="emit('showLog')">查看运行日志</el-button>
        </div>
      </el-empty>
    </div>

    <el-dialog
      v-model="dialogVisible"
      class="metric-curve-dialog"
      title="添加自定义曲线"
      width="min(520px, calc(100vw - 28px))"
      append-to-body
      destroy-on-close
    >
      <el-form label-position="top" @submit.prevent="saveCurve">
        <el-form-item label="曲线名称">
          <el-input v-model="curveDraft.label" maxlength="64" show-word-limit />
        </el-form-item>
        <el-form-item label="计算方式">
          <el-select
            v-model="curveDraft.operation"
            class="dialog-select"
            @change="onOperationChange"
          >
            <el-option
              v-for="operation in operationOptions"
              :key="operation.value"
              :label="operation.label"
              :value="operation.value"
            >
              <div class="operation-option">
                <strong>{{ operation.label }}</strong>
                <span>{{ operation.description }}</span>
              </div>
            </el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="主指标">
          <el-select
            v-model="curveDraft.sourceA"
            class="dialog-select"
            filterable
            @change="onSourceChange"
          >
            <el-option v-for="tag in allTags" :key="tag" :label="tag" :value="tag" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="needsWindow" label="平滑窗口">
          <el-input-number v-model="curveDraft.window" :min="2" :max="500" :step="1" />
        </el-form-item>
        <el-form-item v-if="needsSecondSource" label="第二个指标">
          <el-select v-model="curveDraft.sourceB" class="dialog-select" filterable>
            <el-option
              v-for="tag in allTags"
              :key="tag"
              :label="tag"
              :value="tag"
              :disabled="tag === curveDraft.sourceA"
            />
          </el-select>
        </el-form-item>
        <p v-if="dialogError" class="dialog-error" role="alert">{{ dialogError }}</p>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveCurve">添加曲线</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.metrics-panel {
  width: 100%;
  max-width: 100%;
  min-width: 0;
  min-height: 0;
  height: 100%;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  overflow-x: hidden;
  overflow-y: auto;
  background: var(--surface);
}

.metrics-toolbar {
  width: 100%;
  max-width: 100%;
  box-sizing: border-box;
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  min-height: 54px;
  padding: 9px 12px;
  border-bottom: 1px solid var(--border-subtle);
}

.metric-status {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 9px;
}

.metric-status > div {
  min-width: 0;
  display: grid;
  gap: 2px;
}

.metric-status strong {
  color: var(--text-strong);
  font-size: 12px;
  font-weight: 680;
}

.metric-status span:not(.status-dot) {
  overflow: hidden;
  color: var(--text-muted);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.status-dot {
  width: 9px;
  height: 9px;
  flex: 0 0 auto;
  border: 1px solid color-mix(in srgb, var(--brand) 74%, var(--border-strong));
  border-radius: 50%;
  background: var(--brand);
}

.status-dot.warning {
  border-color: color-mix(in srgb, var(--warning) 74%, var(--border-strong));
  background: var(--warning);
}

.status-dot.quiet {
  border-color: var(--text-faint);
  background: var(--surface);
}

.metric-actions {
  min-width: 0;
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 4px;
}

.metric-group-tabs {
  flex: 0 0 auto;
  display: flex;
  gap: 3px;
  padding: 8px 10px 0;
}

.metric-group-tabs button {
  min-width: 0;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 6px 10px;
  border: 1px solid transparent;
  border-radius: 7px;
  background: transparent;
  color: var(--text-secondary);
  font: inherit;
  font-size: 12px;
  font-weight: 620;
  cursor: pointer;
}

.metric-group-tabs button small {
  min-width: 18px;
  padding: 1px 5px;
  border-radius: 999px;
  background: var(--surface-sunken);
  color: var(--text-muted);
  font-size: 12px;
  text-align: center;
}

.metric-group-tabs button.active {
  border-color: transparent;
  background: var(--brand-softer);
  color: var(--brand-strong);
}

.metric-group-tabs button.active small {
  background: var(--brand-soft);
  color: var(--brand-strong);
}

.metric-group-tabs button:disabled {
  opacity: 0.42;
  cursor: not-allowed;
}

.metric-controls {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 12px;
  padding: 8px 10px;
}

.metric-picker {
  width: min(520px, 68%);
}

.metric-notice {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 0 10px 6px;
  padding: 7px 10px;
  border: 0;
  border-radius: 7px;
  background: color-mix(in srgb, var(--warning) 9%, var(--surface));
  color: var(--text-secondary);
  font-size: 12px;
}

.metric-notice span {
  min-width: 0;
  flex: 1;
}

.metric-notice button {
  flex: 0 0 auto;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--brand-strong);
  font: inherit;
  font-weight: 650;
  cursor: pointer;
}

.metric-chart-shell {
  min-height: 320px;
  flex: 1;
  padding: 0 5px;
}

.metric-loading,
.metric-empty,
.metric-group-empty {
  width: 100%;
  min-width: 0;
  box-sizing: border-box;
  min-height: 320px;
  flex: 1;
  display: grid;
  place-items: center;
  padding: 24px;
}

.metric-empty :deep(.el-empty__description) {
  max-width: 100%;
}

.metric-empty :deep(.el-empty__description p) {
  font-size: 12px;
  line-height: 1.6;
  overflow-wrap: anywhere;
}

.metric-loading {
  display: block;
}

.metric-group-empty {
  align-content: center;
  gap: 5px;
  color: var(--text-muted);
  text-align: center;
}

.metric-group-empty strong {
  color: var(--text-secondary);
  font-size: 13px;
}

.metric-group-empty span {
  font-size: 12px;
}

.empty-actions {
  display: flex;
  justify-content: center;
  gap: 6px;
}

.custom-curve-list {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 7px;
  min-height: 39px;
  overflow-x: auto;
  padding: 6px 10px 8px;
  border-top: 1px solid var(--border-subtle);
  scrollbar-width: thin;
}

.custom-curve-title {
  flex: 0 0 auto;
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 680;
  letter-spacing: 0;
}

.custom-curve-item {
  max-width: 240px;
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 3px 4px 3px 7px;
  border: 0;
  border-radius: 7px;
  background: var(--surface-raised);
}

.custom-curve-item > span {
  min-width: 0;
  overflow: hidden;
  color: var(--text-secondary);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dialog-select {
  width: 100%;
}

.operation-option {
  display: flex;
  align-items: baseline;
  gap: 10px;
}

.operation-option span {
  color: var(--text-muted);
  font-size: 12px;
}

.dialog-error {
  margin: 2px 0 0;
  color: var(--danger);
  font-size: 12px;
}

@media (max-width: 720px) {
  .metrics-toolbar,
  .metric-controls {
    align-items: stretch;
    flex-direction: column;
  }

  .metric-actions {
    width: 100%;
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
    box-sizing: border-box;
    overflow: hidden;
  }

  .metric-actions :deep(.el-button) {
    min-width: 0;
    width: 100%;
    margin-left: 0;
    padding-inline: 8px;
  }

  .metric-picker {
    width: 100%;
  }

  .metric-group-tabs {
    overflow-x: auto;
    padding-bottom: 2px;
  }

  .metric-group-tabs button {
    flex: 0 0 auto;
  }
}

</style>
