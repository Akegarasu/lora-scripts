<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import {
  ArrowLeft,
  CircleCheck,
  Document,
  Picture,
  Refresh,
  Search,
  VideoPause,
  WarningFilled,
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'

import { apiAssetUrl } from '@/api/client'
import type {
  CaptionConflictPolicy,
  CaptionItemState,
  CaptionJobItem,
  CaptionJobState,
} from '@/api/types'
import { useCaptionStore } from '@/stores/caption'

const caption = useCaptionStore()
const router = useRouter()
const query = ref('')
const itemState = ref('')
const commitIds = ref<string[]>([])
const commitPolicy = ref<CaptionConflictPolicy>('skip')
const backupExisting = ref(true)
const logsOpen = ref(false)
const failedImages = ref(new Set<string>())
let searchTimer: number | undefined

const STATE_LABELS: Record<CaptionJobState, string> = {
  created: '已创建',
  queued: '排队中',
  running: '运行中',
  loading: '加载模型',
  generating: '生成中',
  awaiting_review: '等待复核',
  committing: '写入中',
  succeeded: '已完成',
  partial: '部分完成',
  failed: '失败',
  canceling: '正在取消',
  canceled: '已取消',
  interrupted: '已中断',
}

const ITEM_LABELS: Record<CaptionItemState, string> = {
  pending: '等待处理',
  running: '处理中',
  succeeded: '处理成功',
  failed: '失败',
  skipped: '已跳过',
  conflict: '写入冲突',
  canceled: '已取消',
}

const job = computed(() => caption.currentJob)
const progress = computed(() => {
  if (!job.value?.total) return 0
  return Math.min(100, Math.round((job.value.processed / job.value.total) * 100))
})
const reviewable = computed(() =>
  job.value
    ? job.value.reviewMode && ['awaiting_review', 'partial', 'failed'].includes(job.value.state)
    : false,
)
const cancelable = computed(() =>
  job.value
    ? ['created', 'queued', 'running', 'loading', 'generating', 'committing'].includes(job.value.state)
    : false,
)
const writablePageItems = computed(() =>
  caption.currentItems.filter(
    (item) =>
      !item.written &&
      (item.state === 'succeeded' || (item.state === 'failed' && item.edited)),
  ),
)
const selectedSet = computed(() => new Set(commitIds.value))
const pageAllSelected = computed(
  () =>
    writablePageItems.value.length > 0 &&
    writablePageItems.value.every((item) => selectedSet.value.has(item.id)),
)
const currentPage = computed(
  () => Math.floor(caption.currentItemsOffset / caption.currentItemsLimit) + 1,
)
const streamLabel = computed(() => {
  if (caption.streamStatus === 'live') return '实时更新'
  if (caption.streamStatus === 'polling') return '轮询更新'
  if (caption.streamStatus === 'connecting') return '正在连接'
  if (caption.streamStatus === 'ended') return '任务已静止'
  if (caption.streamStatus === 'error') return '更新异常'
  return '等待连接'
})
const logsNeedAttention = computed(() =>
  job.value ? ['failed', 'partial', 'interrupted'].includes(job.value.state) : false,
)
const logText = computed(() =>
  caption.currentLogs
    .map((line) => line.replace(/\u001b\[[0-?]*[ -/]*[@-~]/gu, ''))
    .join('\n'),
)
const lastLogLine = computed(() => {
  const line = caption.currentLogs.at(-1) || ''
  return line.replace(/\u001b\[[0-?]*[ -/]*[@-~]/gu, '')
})

watch(
  () => caption.currentJobId,
  () => {
    commitIds.value = []
    query.value = ''
    itemState.value = ''
  },
)

watch(
  () => job.value?.state,
  (state) => {
    if (state && ['failed', 'partial', 'interrupted'].includes(state)) logsOpen.value = true
  },
  { immediate: true },
)

watch(query, () => {
  if (query.value === caption.currentItemsQuery) return
  if (searchTimer !== undefined) window.clearTimeout(searchTimer)
  searchTimer = window.setTimeout(() => {
    void caption.loadCurrentItems({ offset: 0, query: query.value })
  }, 280)
})

watch(itemState, (state) => {
  if (state === caption.currentItemsState) return
  void caption.loadCurrentItems({ offset: 0, state })
})

onBeforeUnmount(() => {
  if (searchTimer !== undefined) window.clearTimeout(searchTimer)
})

function stateType(state: CaptionJobState) {
  if (state === 'succeeded') return 'success'
  if (state === 'failed' || state === 'canceled' || state === 'interrupted') return 'danger'
  if (state === 'partial' || state === 'awaiting_review') return 'warning'
  return 'primary'
}

function itemType(state: CaptionItemState) {
  if (state === 'succeeded') return 'success'
  if (state === 'failed' || state === 'conflict' || state === 'canceled') return 'danger'
  if (state === 'skipped') return 'info'
  return 'primary'
}

function formatTime(value?: string) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(date)
}

function formatElapsed(value?: number) {
  if (value === undefined || value === null) return ''
  if (value < 1000) return `${value} ms`
  return `${(value / 1000).toFixed(value < 10_000 ? 1 : 0)} 秒`
}

function toggleCommitItem(item: CaptionJobItem, checked: boolean) {
  const next = new Set(commitIds.value)
  if (checked) next.add(item.id)
  else next.delete(item.id)
  commitIds.value = [...next]
}

function togglePage() {
  const next = new Set(commitIds.value)
  for (const item of writablePageItems.value) {
    if (pageAllSelected.value) next.delete(item.id)
    else next.add(item.id)
  }
  commitIds.value = [...next]
}

function changePage(page: number) {
  void caption.loadCurrentItems({ offset: (page - 1) * caption.currentItemsLimit })
}

function markImageFailed(itemId: string) {
  const next = new Set(failedImages.value)
  next.add(itemId)
  failedImages.value = next
}

function canCommitItem(item: CaptionJobItem) {
  return !item.written && (item.state === 'succeeded' || (item.state === 'failed' && item.edited))
}

async function confirmCancel() {
  try {
    await ElMessageBox.confirm(
      '将停止尚未完成的图片处理。已经生成的结果仍会保留在任务记录中。',
      '取消 Caption 任务？',
      { confirmButtonText: '停止任务', cancelButtonText: '继续处理', type: 'warning' },
    )
  } catch {
    return
  }
  const canceled = await caption.cancelCurrentJob()
  if (canceled) ElMessage.success('已发送取消请求')
}

async function commit(selectedOnly: boolean) {
  if (!job.value) return
  const itemIds = selectedOnly ? commitIds.value : undefined
  if (selectedOnly && commitIds.value.length === 0) {
    ElMessage.warning('请先选择要写入的结果')
    return
  }
  const scope = selectedOnly ? `${commitIds.value.length} 个已选结果` : '所有可写结果'
  try {
    await ElMessageBox.confirm(
      `即将把${scope}写入数据集，策略为“${policyLabel(commitPolicy.value)}”。${backupExisting.value ? '已有文件会先创建备份。' : '已有文件不会创建备份。'}`,
      '确认写入 Caption',
      {
        confirmButtonText: '确认写入',
        cancelButtonText: '返回复核',
        type: commitPolicy.value === 'overwrite' || !backupExisting.value ? 'warning' : 'info',
      },
    )
  } catch {
    return
  }
  const committed = await caption.commitCurrentJob({
    itemIds,
    conflictPolicy: commitPolicy.value,
    backupExisting: backupExisting.value,
  })
  if (committed) {
    commitIds.value = []
    ElMessage.success('Caption 写入任务已开始')
  }
}

function policyLabel(policy: CaptionConflictPolicy) {
  const labels: Record<CaptionConflictPolicy, string> = {
    skip: '跳过已有文件',
    fill_empty: '只填充空文件',
    overwrite: '覆盖已有内容',
    prepend: '生成结果放在原内容前',
    append: '生成结果追加到原内容后',
  }
  return labels[policy]
}
</script>

<template>
  <section class="job-detail" aria-labelledby="caption-job-title">
    <header class="job-header">
      <div class="header-copy">
        <el-button text :icon="ArrowLeft" @click="router.push('/caption')">返回 Caption 工作台</el-button>
        <div v-if="job" class="job-title-row">
          <div>
            <h1 id="caption-job-title">{{ job.name || job.modelTitle }}</h1>
            <p>{{ job.modelTitle }} · {{ job.reviewMode ? '生成后复核' : '直接安全写入' }} · {{ job.id }}</p>
          </div>
          <el-tag :type="stateType(job.state)" effect="plain">{{ STATE_LABELS[job.state] }}</el-tag>
        </div>
      </div>
      <div class="header-actions">
        <el-button text :icon="Refresh" :loading="caption.currentLoading" @click="caption.refreshCurrentJob()">
          刷新
        </el-button>
        <el-button
          v-if="cancelable"
          type="danger"
          plain
          :icon="VideoPause"
          :loading="caption.canceling"
          @click="confirmCancel"
        >
          停止任务
        </el-button>
      </div>
    </header>

    <el-alert
      v-if="caption.currentError"
      type="error"
      :title="caption.currentError"
      :closable="false"
      show-icon
    />

    <section v-if="job" class="progress-panel" aria-label="Caption 任务进度">
      <div class="progress-heading">
        <div>
          <span>{{ job.message || STATE_LABELS[job.state] }}</span>
          <strong>{{ job.processed }} / {{ job.total }}</strong>
        </div>
        <el-tag :type="caption.streamStatus === 'error' ? 'danger' : 'info'">
          {{ streamLabel }}
        </el-tag>
      </div>
      <el-progress :percentage="progress" :stroke-width="10" :show-text="false" />
      <div class="progress-stats">
        <span><strong>{{ job.succeeded }}</strong> 成功</span>
        <span><strong>{{ job.written }}</strong> 已写入</span>
        <span><strong>{{ job.skipped }}</strong> 已跳过</span>
        <span :class="{ danger: job.failed > 0 }"><strong>{{ job.failed }}</strong> 失败</span>
        <span :class="{ danger: job.conflicts > 0 }"><strong>{{ job.conflicts }}</strong> 冲突</span>
        <span>创建于 {{ formatTime(job.createdAt) }}</span>
      </div>
      <p v-if="caption.streamError" class="stream-note">{{ caption.streamError }}</p>
      <p v-if="job.errorMessage" class="job-error">{{ job.errorMessage }}</p>
    </section>

    <section
      v-if="job"
      class="log-panel"
      :class="{ attention: logsNeedAttention, expanded: logsOpen }"
      aria-labelledby="caption-log-title"
    >
      <div class="log-heading">
        <button type="button" :aria-expanded="logsOpen" @click="logsOpen = !logsOpen">
          <span class="log-icon"><el-icon><Document /></el-icon></span>
          <span>
            <strong id="caption-log-title">运行日志</strong>
            <small v-if="logsNeedAttention">任务没有完全成功，日志已展开以便定位原因。</small>
            <small v-else-if="lastLogLine" class="last-log-line">{{ lastLogLine }}</small>
            <small v-else>暂无日志</small>
          </span>
          <el-tag v-if="caption.currentLogs.length" type="info">最近 {{ caption.currentLogs.length }} 行</el-tag>
          <span class="log-toggle-label">{{ logsOpen ? '收起' : '展开' }}</span>
        </button>
        <el-button
          v-if="logsOpen"
          plain
          :icon="Refresh"
          :loading="caption.logsLoading"
          @click="caption.loadCurrentLogs()"
        >
          刷新日志
        </el-button>
      </div>
      <div v-if="logsOpen" class="log-content" aria-live="polite">
        <el-alert
          v-if="caption.logsError"
          type="error"
          :title="caption.logsError"
          :closable="false"
          show-icon
        />
        <pre v-if="logText">{{ logText }}</pre>
        <div v-else-if="!caption.logsLoading" class="log-empty">当前还没有运行日志。</div>
      </div>
    </section>

    <section v-if="job" class="review-panel">
      <div class="review-heading">
        <div>
          <h2>{{ job.reviewMode ? (reviewable ? '检查并提交抽样结果' : '复核任务明细') : '执行明细与异常' }}</h2>
        </div>
        <span class="result-summary">当前筛选 {{ caption.currentItemsTotal }} 项</span>
      </div>

      <el-alert
        v-if="!job.reviewMode"
        type="info"
        :title="job.detailsState === 'compacted' ? '任务详情已轻量化保存' : '人工编辑已从批量生成流程中分离'"
        :description="job.detailsState === 'compacted'
          ? 'Caption 文件是最终数据源；成功项的临时文本和标签已清理，状态与异常仍保留。长期修订请使用人工编辑工作台。'
          : '直接写入任务完成后会压缩临时详情；查找、批量替换和人工打标请使用人工编辑工作台。'"
        :closable="false"
        show-icon
      />

      <div class="review-toolbar">
        <el-input
          v-model="query"
          :prefix-icon="Search"
          clearable
          placeholder="搜索文件名"
          aria-label="搜索任务结果"
        />
        <el-select v-model="itemState" clearable placeholder="全部状态" aria-label="筛选结果状态">
          <el-option label="等待处理" value="pending" />
          <el-option label="处理中" value="running" />
          <el-option label="已生成" value="succeeded" />
          <el-option label="失败" value="failed" />
          <el-option label="已跳过" value="skipped" />
          <el-option label="写入冲突" value="conflict" />
          <el-option label="已取消" value="canceled" />
        </el-select>
        <el-button
          v-if="reviewable"
          :disabled="writablePageItems.length === 0"
          @click="togglePage"
        >
          {{ pageAllSelected ? '取消选择本页' : '选择本页可写结果' }}
        </el-button>
      </div>

      <div v-loading="caption.currentLoading" class="result-list">
        <article v-for="item in caption.currentItems" :key="item.id" class="result-card">
          <div class="result-media">
            <img
              v-if="!failedImages.has(item.id)"
              :src="apiAssetUrl(item.thumbnailUrl)"
              :alt="item.name"
              loading="lazy"
              @error="markImageFailed(item.id)"
            />
            <div v-else class="image-fallback">
              <el-icon><Picture /></el-icon>
              <span>无法预览</span>
            </div>
            <el-checkbox
              v-if="reviewable && canCommitItem(item)"
              class="commit-check"
              :model-value="selectedSet.has(item.id)"
              :aria-label="`选择写入 ${item.name}`"
              @change="(checked: boolean | string | number) => toggleCommitItem(item, Boolean(checked))"
            />
          </div>

          <div class="result-content">
            <div class="result-title">
              <div>
                <strong>{{ item.name }}</strong>
                <span :title="item.relativePath">{{ item.relativePath }}</span>
              </div>
              <div class="result-badges">
                <el-tag :type="itemType(item.state)">{{ ITEM_LABELS[item.state] }}</el-tag>
                <el-tag v-if="item.written" type="success">已写入</el-tag>
                <el-tag v-else-if="item.edited" type="warning">已人工修改</el-tag>
                <span v-if="item.elapsedMs !== undefined">{{ formatElapsed(item.elapsedMs) }}</span>
              </div>
            </div>

            <p v-if="item.error" class="item-error">
              <el-icon><WarningFilled /></el-icon>
              {{ item.error }}
            </p>

            <div v-if="job.reviewMode" class="comparison-grid">
              <div class="text-block">
                <span>原 Caption</span>
                <p :class="{ empty: !item.existingText }">{{ item.existingText || '无' }}</p>
              </div>
              <div class="text-block">
                <span>模型生成</span>
                <p :class="{ empty: !item.generatedText }">{{ item.generatedText || '尚未生成' }}</p>
              </div>
              <div class="text-block">
                <span>计划写入</span>
                <p :class="{ empty: !item.finalText }">{{ item.finalText || '无可写内容' }}</p>
              </div>
            </div>

            <div v-else class="direct-result-summary">
              <strong>{{ item.written ? 'Caption 已安全写入' : ITEM_LABELS[item.state] }}</strong>
              <span v-if="item.state === 'skipped'">已有 Caption 按当前策略保留。</span>
              <span v-else-if="item.error">请根据上方错误信息检查该图片。</span>
              <span v-else-if="item.written">临时生成内容无需长期保存在任务数据库中。</span>
              <span v-else>任务仍在处理，状态会自动更新。</span>
            </div>

            <div v-if="item.tags.length" class="tag-list" aria-label="模型返回标签">
              <el-tag v-for="tag in item.tags.slice(0, 18)" :key="`${tag.category}-${tag.text}`" type="info">
                {{ tag.text }}<span v-if="tag.score != null"> {{ Math.round(tag.score * 100) }}%</span>
              </el-tag>
              <span v-if="item.tags.length > 18">另有 {{ item.tags.length - 18 }} 个标签</span>
            </div>

          </div>
        </article>

        <div v-if="!caption.currentLoading && caption.currentItems.length === 0" class="empty-result">
          <el-icon><Picture /></el-icon>
          <strong>没有符合条件的结果</strong>
          <span>任务可能尚未生成结果，或当前筛选条件过窄。</span>
        </div>
      </div>

      <el-pagination
        v-if="caption.currentItemsTotal > caption.currentItemsLimit"
        class="result-pagination"
        background
        layout="prev, pager, next"
        :current-page="currentPage"
        :page-size="caption.currentItemsLimit"
        :total="caption.currentItemsTotal"
        @current-change="changePage"
      />
    </section>

    <section v-if="reviewable" class="commit-panel" aria-label="提交 Caption">
      <div class="commit-copy">
        <el-icon><CircleCheck /></el-icon>
        <div>
          <strong>复核完成后写入数据集</strong>
          <span>已选择 {{ commitIds.length }} 项；可逐页检查后写入，长期修订请使用人工编辑工作台。</span>
        </div>
      </div>
      <div class="commit-options">
        <label>
          <span>已有 Caption 的处理方式</span>
          <el-select v-model="commitPolicy">
            <el-option label="跳过已有文件（最安全）" value="skip" />
            <el-option label="只填充空文件" value="fill_empty" />
            <el-option label="覆盖已有内容" value="overwrite" />
            <el-option label="生成结果放在原内容前" value="prepend" />
            <el-option label="生成结果追加到原内容后" value="append" />
          </el-select>
        </label>
        <label class="backup-switch">
          <span>
            <strong>备份已有文件</strong>
            <small>防止覆盖后无法恢复。</small>
          </span>
          <el-switch v-model="backupExisting" />
        </label>
      </div>
      <div class="commit-actions">
        <el-button
          :disabled="commitIds.length === 0"
          :loading="caption.committing"
          @click="commit(true)"
        >
          写入已选 {{ commitIds.length || '' }} 项
        </el-button>
        <el-button type="primary" :loading="caption.committing" @click="commit(false)">
          写入所有可用结果
        </el-button>
      </div>
    </section>

    <div v-if="!job && !caption.currentLoading" class="job-missing">
      <el-icon><WarningFilled /></el-icon>
      <strong>无法加载这个 Caption 任务</strong>
      <el-button @click="router.push('/caption')">返回工作台</el-button>
    </div>
  </section>
</template>

<style scoped>
.job-detail {
  width: min(100%, var(--page-max));
  min-height: 100dvh;
  margin: 0 auto;
  display: grid;
  align-content: start;
  gap: 18px;
  padding: 30px clamp(20px, 3vw, 48px) 54px;
}

.job-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
}

.header-copy {
  min-width: 0;
}

.header-copy > .el-button {
  margin: 0 0 11px -14px;
}

.job-title-row {
  display: flex;
  align-items: flex-start;
  gap: 14px;
}

.job-title-row > div {
  min-width: 0;
}

.eyebrow {
  color: var(--brand-strong);
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.04em;
}

.job-title-row h1 {
  margin: 3px 0 0;
  color: var(--text-strong);
  font-family: var(--font-display);
  font-size: var(--font-page-title);
  font-weight: 730;
  letter-spacing: -0.025em;
}

.job-title-row p {
  margin: 5px 0 0;
  overflow-wrap: anywhere;
  color: var(--text-muted);
  font-size: 14px;
}

.header-actions {
  display: flex;
  gap: 9px;
}

.progress-panel,
.log-panel,
.review-panel,
.commit-panel {
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  background: var(--surface);
}

.progress-panel,
.review-panel {
  border: 0;
  border-radius: 0;
  background: transparent;
}

.progress-panel {
  display: grid;
  gap: 13px;
  padding: 18px;
}

.progress-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.progress-heading > div {
  min-width: 0;
  display: flex;
  align-items: baseline;
  gap: 10px;
}

.progress-heading span {
  color: var(--text-secondary);
  font-size: 14px;
}

.progress-heading strong {
  color: var(--text-strong);
  font-size: 18px;
}

.progress-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 18px;
  color: var(--text-muted);
  font-size: 13px;
}

.progress-stats strong {
  color: var(--text-strong);
}

.progress-stats .danger,
.progress-stats .danger strong {
  color: var(--danger);
}

.stream-note,
.job-error {
  margin: 0;
  color: var(--warning);
  font-size: 13px;
}

.job-error {
  color: var(--danger);
}

.log-panel {
  overflow: hidden;
}

.log-panel.attention {
  border-color: color-mix(in srgb, var(--danger) 44%, var(--border));
  background: color-mix(in srgb, var(--danger) 3%, var(--surface));
}

.log-heading {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
}

.log-heading > button {
  min-width: 0;
  flex: 1;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto auto;
  align-items: center;
  gap: 10px;
  padding: 0;
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.log-icon {
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  border-radius: 8px;
  background: var(--surface-sunken);
  color: var(--text-secondary);
  font-size: 17px;
}

.attention .log-icon {
  background: var(--danger-soft);
  color: var(--danger);
}

.log-heading > button > span:nth-child(2) {
  min-width: 0;
  display: grid;
  gap: 2px;
}

.log-heading strong {
  color: var(--text-strong);
  font-size: 14px;
}

.log-heading small {
  overflow: hidden;
  color: var(--text-muted);
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.attention .log-heading small {
  color: var(--danger);
}

.log-toggle-label {
  color: var(--brand-strong);
  font-size: 13px;
  font-weight: 650;
}

.log-content {
  display: grid;
  gap: 10px;
  padding: 0 14px 14px;
}

.log-content pre {
  max-height: 360px;
  margin: 0;
  overflow: auto;
  padding: 14px;
  border: 1px solid var(--border-subtle);
  border-radius: 9px;
  background: var(--canvas-tint);
  color: var(--text);
  font-family: var(--font-mono);
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.log-empty {
  min-height: 90px;
  display: grid;
  place-items: center;
  border-radius: 9px;
  background: var(--surface-sunken);
  color: var(--text-muted);
  font-size: 13px;
}

.review-panel {
  display: grid;
  gap: 16px;
  padding: 24px 0;
  border-top: 1px solid var(--border-subtle);
}

.review-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.review-heading h2 {
  margin: 3px 0 0;
  color: var(--text-strong);
  font-size: 20px;
  font-weight: 700;
}

.review-heading p {
  margin: 5px 0 0;
  color: var(--text-muted);
  font-size: 14px;
}

.result-summary {
  color: var(--text-muted);
  font-size: 13px;
}

.review-toolbar {
  display: grid;
  grid-template-columns: minmax(220px, 1fr) 180px auto;
  gap: 10px;
}

.result-list {
  min-height: 180px;
  display: grid;
  gap: 12px;
}

.result-card {
  min-width: 0;
  display: grid;
  grid-template-columns: 190px minmax(0, 1fr);
  overflow: hidden;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  background: var(--surface-sunken);
}

.result-media {
  position: relative;
  min-height: 190px;
  background: var(--canvas-tint);
}

.result-media img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.image-fallback {
  height: 100%;
  display: grid;
  place-items: center;
  align-content: center;
  gap: 7px;
  color: var(--text-muted);
  font-size: 13px;
}

.image-fallback .el-icon {
  font-size: 27px;
}

.commit-check {
  position: absolute;
  top: 10px;
  left: 10px;
  min-width: 32px;
  min-height: 32px;
  display: grid;
  place-items: center;
  border-radius: 7px;
  background: rgb(20 20 20 / 62%);
}

.commit-check :deep(.el-checkbox__label) {
  display: none;
}

.result-content {
  min-width: 0;
  display: grid;
  align-content: start;
  gap: 12px;
  padding: 14px;
}

.result-title {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}

.result-title > div:first-child {
  min-width: 0;
  display: grid;
  gap: 3px;
}

.result-title strong {
  color: var(--text-strong);
  font-size: 15px;
}

.result-title span {
  overflow: hidden;
  color: var(--text-muted);
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.result-badges {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 6px;
}

.comparison-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 9px;
}

.direct-result-summary {
  display: grid;
  gap: 4px;
  padding: 11px 12px;
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  background: var(--surface-sunken);
}

.direct-result-summary strong {
  color: var(--text-strong);
  font-size: 14px;
}

.direct-result-summary span {
  color: var(--text-muted);
  font-size: 13px;
  line-height: 1.5;
}

.text-block {
  min-width: 0;
  display: grid;
  align-content: start;
  gap: 6px;
}

.text-block > span {
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 650;
}

.text-block p {
  min-height: 100px;
  max-height: 150px;
  margin: 0;
  overflow: auto;
  padding: 10px;
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  background: var(--surface);
  color: var(--text);
  font-size: 13px;
  line-height: 1.55;
  white-space: pre-wrap;
}

.text-block p.empty {
  color: var(--text-muted);
}

.item-error {
  margin: 0;
  display: flex;
  align-items: flex-start;
  gap: 6px;
  color: var(--danger);
  font-size: 13px;
}

.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.tag-list > span:last-child {
  align-self: center;
  color: var(--text-muted);
  font-size: 13px;
}

.result-pagination {
  justify-self: center;
}

.empty-result,
.job-missing {
  min-height: 190px;
  display: grid;
  place-items: center;
  align-content: center;
  gap: 8px;
  color: var(--text-muted);
  text-align: center;
}

.empty-result .el-icon,
.job-missing .el-icon {
  font-size: 30px;
}

.empty-result strong,
.job-missing strong {
  color: var(--text-strong);
  font-size: 15px;
}

.empty-result span {
  font-size: 13px;
}

.commit-panel {
  position: sticky;
  z-index: 8;
  bottom: 14px;
  display: grid;
  grid-template-columns: minmax(220px, 0.7fr) minmax(340px, 1fr) auto;
  align-items: center;
  gap: 18px;
  padding: 16px 18px;
  box-shadow: 0 8px 28px rgb(0 0 0 / 10%);
}

.commit-copy {
  display: flex;
  align-items: center;
  gap: 11px;
}

.commit-copy > .el-icon {
  color: var(--success);
  font-size: 25px;
}

.commit-copy > div {
  display: grid;
  gap: 2px;
}

.commit-copy strong {
  color: var(--text-strong);
  font-size: 14px;
}

.commit-copy span {
  color: var(--text-muted);
  font-size: 13px;
}

.commit-options {
  display: grid;
  grid-template-columns: minmax(210px, 1fr) minmax(180px, 0.7fr);
  gap: 10px;
}

.commit-options > label {
  min-width: 0;
  display: grid;
  gap: 5px;
}

.commit-options > label > span {
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 620;
}

.backup-switch {
  display: flex !important;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 7px 10px;
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  background: var(--surface-sunken);
}

.backup-switch > span {
  display: grid;
  gap: 1px;
}

.backup-switch strong {
  color: var(--text-strong);
  font-size: 13px;
}

.backup-switch small {
  color: var(--text-muted);
  font-size: 13px;
}

.commit-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

@media (max-width: 1180px) {
  .comparison-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .commit-panel {
    position: static;
    grid-template-columns: 1fr;
  }
}

@media (max-width: 760px) {
  .job-detail {
    padding: 18px 14px 34px;
  }

  .job-header,
  .job-title-row,
  .review-heading {
    display: grid;
  }

  .header-actions {
    width: 100%;
  }

  .header-actions .el-button {
    flex: 1;
  }

  .log-heading {
    align-items: stretch;
    flex-direction: column;
  }

  .log-heading > button {
    grid-template-columns: auto minmax(0, 1fr) auto;
  }

  .log-heading .el-tag {
    display: none;
  }

  .review-panel {
    padding: 14px;
  }

  .review-toolbar,
  .comparison-grid,
  .commit-options {
    grid-template-columns: 1fr;
  }

  .result-card {
    grid-template-columns: 1fr;
  }

  .result-media {
    min-height: 0;
    aspect-ratio: 16 / 9;
  }

  .result-title {
    display: grid;
  }

  .result-badges {
    justify-content: flex-start;
  }

  .commit-actions {
    display: grid;
  }
}
</style>
