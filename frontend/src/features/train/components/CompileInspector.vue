<script setup lang="ts">
import { computed, ref } from 'vue'
import { Check, CopyDocument, DocumentChecked, Promotion, WarningFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

import type { ParamDefinition, ValidationMessage } from '@/api/types'
import { useCatalogStore } from '@/stores/catalog'
import { useDraftStore } from '@/stores/draft'
import { useJobsStore } from '@/stores/jobs'

const props = defineProps<{
  missingParams: ParamDefinition[]
  previewFresh: boolean
}>()

const emit = defineEmits<{
  compile: []
  start: []
  locate: [targetId: string]
}>()

const catalog = useCatalogStore()
const draft = useDraftStore()
const jobs = useJobsStore()
const previewTab = ref('train')

const localChecks = computed(() => [
  {
    id: 'trainer',
    label: '训练器',
    detail: catalog.selectedTrainer?.title || '尚未选择',
    done: !!catalog.selectedTrainerId,
  },
  {
    id: 'assets',
    label: '必要资产',
    detail: props.missingParams.length ? `还缺 ${props.missingParams.length} 项` : '已填写',
    done: props.missingParams.length === 0,
  },
  {
    id: 'dataset',
    label: '训练数据',
    detail: draft.dataset.root || '尚未选择目录',
    done: !!draft.dataset.root.trim(),
  },
  {
    id: 'output',
    label: '输出名称',
    detail: draft.name.trim() || '尚未命名',
    done: !!draft.name.trim(),
  },
  ...(draft.sample.enabled
    ? [
        {
          id: 'sampling',
          label: '采样预览',
          detail: draft.sample.prompts.some((item) => !!item.prompt.trim()) ? '已填写' : '尚未填写 Prompt',
          done: draft.sample.prompts.some((item) => !!item.prompt.trim()),
        },
      ]
    : []),
])

const completedChecks = computed(() => localChecks.value.filter((item) => item.done).length)
const readiness = computed(() => Math.round((completedChecks.value / localChecks.value.length) * 100))
const compileErrors = computed(() => draft.compileResult?.errors || [])
const compileWarnings = computed(() => draft.compileResult?.warnings || [])
const localReady = computed(() => localChecks.value.every((item) => item.done))
const compiledClean = computed(
  () => props.previewFresh && !!draft.compileResult && compileErrors.value.length === 0,
)

const readinessLabel = computed(() => {
  if (!localReady.value) return '仍需补充配置'
  if (draft.compiling) return '正在检查配置'
  if (!draft.compileResult || !props.previewFresh) return '可以开始预检'
  if (compileErrors.value.length) return '预检发现问题'
  return compileWarnings.value.length ? '可启动，存在提醒' : '已通过预检'
})

const previewText = computed(() => {
  if (!draft.compileResult) return ''
  if (previewTab.value === 'train') return draft.compileResult.trainConfig || ''
  if (previewTab.value === 'dataset') return draft.compileResult.datasetConfig || ''
  if (previewTab.value === 'sample') return draft.compileResult.samplePrompts || ''
  return draft.compileResult.command?.join(' \\\n  ') || ''
})

function issueTarget(issue: ValidationMessage) {
  const field = issue.field || ''
  if (field.includes('dataset')) return 'section-dataset'
  if (field.includes('sample')) return 'section-sampling'
  if (field === 'name' || field.includes('output_name')) return 'output-name'
  if (field.includes('runtime.gpu')) return 'gpu-select'
  if (field.includes('runtime')) return 'section-runtime'
  const name = field.split('.').pop()
  return name ? `param-${name}` : ''
}

function focusIssue(issue: ValidationMessage) {
  const target = issueTarget(issue)
  if (target) emit('locate', target)
}

async function copyPreview() {
  if (!previewText.value) return
  try {
    await navigator.clipboard.writeText(previewText.value)
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.error('复制失败，请手动选择文本')
  }
}
</script>

<template>
  <aside class="compile-inspector" aria-label="配置检查与启动">
    <section class="readiness-card">
      <div class="readiness-head">
        <div class="progress-ring" :style="{ '--progress': `${readiness * 3.6}deg` }">
          <span>{{ readiness }}<small>%</small></span>
        </div>
        <div>
          <h2>{{ readinessLabel }}</h2>
          <p>{{ completedChecks }} / {{ localChecks.length }} 项基础检查完成</p>
        </div>
      </div>

      <div class="check-list">
        <div v-for="item in localChecks" :key="item.id" class="check-item" :class="{ done: item.done }">
          <span class="check-icon" aria-hidden="true">
            <el-icon v-if="item.done"><Check /></el-icon>
            <span v-else />
          </span>
          <span>
            <strong>{{ item.label }}</strong>
            <small :title="item.detail">{{ item.detail }}</small>
          </span>
        </div>
      </div>
    </section>

    <section v-if="compileErrors.length || compileWarnings.length || draft.compileError" class="issues-card">
      <header>
        <div>
          <h2>
            {{ compileErrors.length ? `${compileErrors.length} 个问题` : `${compileWarnings.length} 条提醒` }}
          </h2>
        </div>
        <el-icon :class="compileErrors.length ? 'danger' : 'warning'"><WarningFilled /></el-icon>
      </header>

      <button
        v-for="issue in compileErrors"
        :key="`${issue.code}-${issue.field}`"
        class="issue-line danger"
        type="button"
        @click="focusIssue(issue)"
      >
        <strong>{{ issue.message }}</strong>
        <small v-if="issue.field">{{ issue.field }} · 点击定位</small>
      </button>
      <button
        v-for="issue in compileWarnings"
        :key="`${issue.code}-${issue.field}`"
        class="issue-line warning"
        type="button"
        @click="focusIssue(issue)"
      >
        <strong>{{ issue.message }}</strong>
        <small v-if="issue.field">{{ issue.field }} · 点击定位</small>
      </button>
      <div v-if="draft.compileError" class="issue-line danger static">{{ draft.compileError }}</div>
    </section>

    <section class="preview-card" :class="{ stale: draft.compileResult && !previewFresh }">
      <header class="preview-header">
        <div>
          <h2>{{ draft.compileResult ? '运行配置快照' : '等待首次预检' }}</h2>
        </div>
        <el-button
          v-if="draft.compileResult"
          text
          circle
          :icon="CopyDocument"
          aria-label="复制当前预览"
          @click="copyPreview"
        />
      </header>

      <div v-if="draft.compileResult && !previewFresh" class="stale-notice">
        草稿已修改，当前预览不是最新版本。
      </div>

      <template v-if="draft.compileResult">
        <el-tabs v-model="previewTab" class="preview-tabs">
          <el-tab-pane label="训练" name="train" />
          <el-tab-pane label="数据集" name="dataset" />
          <el-tab-pane label="采样" name="sample" />
          <el-tab-pane label="命令" name="command" />
        </el-tabs>
        <pre>{{ previewText || '此配置未生成内容' }}</pre>
      </template>

      <div v-else class="preview-empty">
        <span><el-icon><DocumentChecked /></el-icon></span>
        <strong>生成 TOML 与启动命令</strong>
        <p>预检不会启动训练，也不会写入正式 Run 目录。</p>
      </div>
    </section>

    <section class="launch-card">
      <div class="launch-summary">
        <span>
          <small>训练器</small>
          <strong>{{ catalog.selectedTrainer?.family?.toUpperCase() || '—' }}</strong>
        </span>
        <span>
          <small>GPU</small>
          <strong>{{ draft.runtime.gpuIds.length ? draft.runtime.gpuIds.join(', ') : '自动' }}</strong>
        </span>
        <span>
          <small>输出名</small>
          <strong :title="draft.name">{{ draft.name || '—' }}</strong>
        </span>
      </div>

      <el-button
        class="compile-button"
        size="large"
        :loading="draft.compiling"
        :disabled="!catalog.selectedTrainerId"
        :icon="DocumentChecked"
        @click="emit('compile')"
      >
        {{ previewFresh && draft.compileResult ? '重新预检' : '检查配置' }}
      </el-button>
      <el-tooltip
        :disabled="localReady"
        content="请先补全上方列出的训练准备项"
        placement="top"
      >
        <span class="start-wrap">
          <el-button
            class="start-button"
            type="primary"
            size="large"
            :loading="jobs.starting || draft.compiling"
            :disabled="!localReady"
            :icon="Promotion"
            @click="emit('start')"
          >
            检查并开始训练
          </el-button>
        </span>
      </el-tooltip>
      <p>
        <template v-if="compiledClean">当前草稿已通过非路径预检；启动时仍会检查真实文件。</template>
        <template v-else>启动前会使用最新草稿执行完整路径校验。</template>
      </p>
    </section>
  </aside>
</template>

<style scoped>
.compile-inspector {
  display: grid;
  gap: 14px;
}

.readiness-card,
.issues-card,
.preview-card,
.launch-card {
  overflow: hidden;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: none;
}

.readiness-card,
.issues-card,
.launch-card {
  padding: 4px 2px 18px;
}

.readiness-card,
.issues-card {
  border-bottom: 1px solid var(--border-subtle) !important;
  border-radius: 0 !important;
}

.readiness-head {
  display: flex;
  align-items: center;
  gap: 13px;
}

.progress-ring {
  flex: 0 0 58px;
  width: 58px;
  height: 58px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background:
    radial-gradient(circle at center, var(--surface) 57%, transparent 59%),
    conic-gradient(var(--brand) var(--progress), var(--border-subtle) 0);
}

.progress-ring > span {
  color: var(--text-strong);
  font-family: var(--font-display);
  font-size: 16px;
  font-weight: 720;
}

.progress-ring small {
  margin-left: 1px;
  color: var(--text-muted);
  font-size: 9px;
}

.eyebrow {
  color: var(--text-muted);
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.09em;
  text-transform: uppercase;
}

h2 {
  margin: 3px 0 0;
  color: var(--text-strong);
  font-size: 13px;
  font-weight: 680;
}

.readiness-head p {
  margin: 4px 0 0;
  color: var(--text-muted);
  font-size: 10px;
}

.check-list {
  display: grid;
  gap: 2px;
  margin-top: 16px;
}

.check-item {
  display: grid;
  grid-template-columns: 22px minmax(0, 1fr);
  align-items: center;
  gap: 7px;
  min-height: 39px;
  padding: 5px 3px;
  border-top: 1px solid var(--border-subtle);
}

.check-icon {
  width: 18px;
  height: 18px;
  display: grid;
  place-items: center;
  border: 1px solid var(--border-strong);
  border-radius: 50%;
  color: var(--text-muted);
  font-size: 10px;
}

.check-item.done .check-icon {
  border-color: color-mix(in srgb, var(--success) 24%, transparent);
  background: var(--success-soft);
  color: var(--success);
}

.check-item > span:last-child {
  min-width: 0;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: baseline;
  gap: 8px;
}

.check-item strong {
  color: var(--text);
  font-size: 10px;
  font-weight: 620;
}

.check-item small {
  overflow: hidden;
  color: var(--text-muted);
  font-size: 9px;
  text-align: right;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.issues-card {
  display: grid;
  gap: 8px;
}

.issues-card > header,
.preview-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.issues-card > header > .el-icon {
  font-size: 19px;
}

.danger {
  color: var(--danger);
}

.warning {
  color: var(--warning);
}

.issue-line {
  width: 100%;
  display: grid;
  gap: 3px;
  padding: 8px 9px;
  border: 0;
  border-radius: var(--radius-sm);
  background: transparent;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.issue-line.danger {
  background: var(--danger-soft);
  color: var(--danger);
}

.issue-line.warning {
  background: var(--warning-soft);
  color: var(--warning);
}

.issue-line strong,
.issue-line.static {
  font-size: 10px;
  font-weight: 600;
  line-height: 1.45;
}

.issue-line small {
  opacity: 0.72;
  font-size: 9px;
}

.issue-line.static {
  cursor: default;
}

.preview-card {
  position: relative;
}

.preview-card.stale::after {
  position: absolute;
  inset: 0;
  z-index: 1;
  background: color-mix(in srgb, var(--surface) 12%, transparent);
  pointer-events: none;
  content: '';
}

.preview-header {
  padding: 14px 15px 9px;
}

.stale-notice {
  position: relative;
  z-index: 2;
  margin: 0 12px 6px;
  padding: 7px 9px;
  border-radius: 7px;
  background: var(--warning-soft);
  color: var(--warning);
  font-size: 9px;
  font-weight: 560;
}

.preview-tabs {
  position: relative;
  z-index: 2;
  padding: 0 12px;
}

.preview-tabs :deep(.el-tabs__header) {
  margin: 0;
}

.preview-tabs :deep(.el-tabs__item) {
  height: 34px;
  padding: 0 9px;
  font-size: 10px;
}

.preview-tabs :deep(.el-tabs__content) {
  display: none;
}

pre {
  position: relative;
  z-index: 2;
  max-height: 330px;
  min-height: 100px;
  overflow: auto;
  margin: 0;
  padding: 12px 14px 15px;
  border-top: 1px solid var(--border-subtle);
  background: var(--surface-sunken);
  color: var(--text-secondary);
  font-size: 9px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.preview-empty {
  min-height: 170px;
  display: grid;
  place-items: center;
  align-content: center;
  gap: 6px;
  padding: 20px;
  color: var(--text-muted);
  text-align: center;
}

.preview-empty > span {
  width: 38px;
  height: 38px;
  display: grid;
  place-items: center;
  margin-bottom: 3px;
  border-radius: 11px;
  background: var(--surface-sunken);
  color: var(--brand-strong);
  font-size: 18px;
}

.preview-empty strong {
  color: var(--text-secondary);
  font-size: 11px;
}

.preview-empty p {
  max-width: 220px;
  margin: 0;
  font-size: 9px;
  line-height: 1.5;
}

.launch-card {
  display: grid;
  gap: 9px;
  background: transparent;
}

.launch-summary {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 3px;
}

.launch-summary > span {
  min-width: 0;
  display: grid;
  gap: 2px;
}

.launch-summary small {
  color: var(--text-muted);
  font-size: 8px;
}

.launch-summary strong {
  overflow: hidden;
  color: var(--text-strong);
  font-size: 10px;
  font-weight: 650;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.compile-button,
.start-button,
.start-wrap {
  width: 100%;
}

.start-wrap {
  display: block;
}

.launch-card > p {
  margin: 1px 2px 0;
  color: var(--text-muted);
  font-size: 9px;
  line-height: 1.45;
  text-align: center;
}

.progress-ring small,
.launch-summary small {
  font-size: 12px;
}

.eyebrow,
.check-item small,
.issue-line small,
.stale-notice,
.preview-empty p,
.launch-card > p {
  font-size: 12px;
}

.readiness-head p,
.check-item strong,
.issue-line strong,
.issue-line.static,
.preview-tabs :deep(.el-tabs__item),
pre,
.launch-summary strong {
  font-size: 13px;
}

h2,
.preview-empty strong {
  font-size: 14px;
}
</style>
