<script setup lang="ts">
import { Check, DocumentChecked, RefreshRight, WarningFilled } from '@element-plus/icons-vue'
import { computed, ref, watch } from 'vue'

import type {
  TagEditorChangeResult,
  TagEditorChangeResultState,
  TagEditorChangeState,
  TagEditorPreviewResponse,
} from '@/api/types'

type PreviewWithWarnings = TagEditorPreviewResponse & { warnings?: string[] }

const props = defineProps<{
  modelValue: boolean
  preview: PreviewWithWarnings | null
  applying: boolean
  refreshing?: boolean
  results?: TagEditorChangeResult[]
  resultsTotal?: number
  resultsLoading?: boolean
  resultsError?: string
  readonly?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  apply: [backupExisting: boolean]
  refresh: []
}>()

const backupExisting = ref(true)
const visible = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value),
})
const changeSet = computed(() => props.preview || null)
const canApply = computed(
  () => !props.readonly && changeSet.value?.state === 'previewed' && (changeSet.value?.changed || 0) > 0,
)
const isRunning = computed(() =>
  ['queued', 'applying', 'rolling_back'].includes(changeSet.value?.state || ''),
)

watch(
  () => props.preview?.id,
  () => {
    backupExisting.value = true
  },
)

const STATE_LABEL: Record<TagEditorChangeState, string> = {
  previewed: '等待确认',
  queued: '已排队',
  applying: '正在应用',
  completed: '应用完成',
  partial: '部分完成',
  failed: '应用失败',
  rolling_back: '正在回滚',
  rolled_back: '已回滚',
  rollback_partial: '部分回滚',
  interrupted: '已中断',
}

function stateType(state?: TagEditorChangeState) {
  if (state === 'completed' || state === 'rolled_back') return 'success'
  if (state === 'partial' || state === 'rollback_partial' || state === 'previewed') return 'warning'
  if (state === 'failed') return 'danger'
  return 'info'
}

const RESULT_LABEL: Record<TagEditorChangeResultState, string> = {
  applied: '已应用',
  conflict: '冲突',
  failed: '失败',
  rolled_back: '已回滚',
  rollback_conflict: '回滚冲突',
}

function resultType(state: TagEditorChangeResultState) {
  if (state === 'applied' || state === 'rolled_back') return 'success'
  if (state === 'conflict' || state === 'rollback_conflict') return 'warning'
  return 'danger'
}
</script>

<template>
  <el-dialog
    v-model="visible"
    class="change-preview-dialog"
    title="变更预览"
    width="min(1080px, calc(100vw - 24px))"
    destroy-on-close
    :close-on-click-modal="!applying"
    :close-on-press-escape="!applying"
  >
    <div v-if="preview && changeSet" class="preview-content">
      <header class="preview-header">
        <div class="preview-title">
          <span class="preview-icon"><el-icon><DocumentChecked /></el-icon></span>
          <div>
            <span>变更集 {{ changeSet.id }}</span>
            <strong>{{ STATE_LABEL[changeSet.state] }}</strong>
          </div>
        </div>
        <el-tag :type="stateType(changeSet.state)">{{ STATE_LABEL[changeSet.state] }}</el-tag>
      </header>

      <div class="stat-grid" aria-label="变更统计">
        <div><span>作用范围</span><strong>{{ changeSet.matched }}</strong></div>
        <div class="changed"><span>将修改</span><strong>{{ changeSet.changed }}</strong></div>
        <div><span>不变</span><strong>{{ changeSet.unchanged }}</strong></div>
        <div class="warning"><span>冲突</span><strong>{{ changeSet.conflicts }}</strong></div>
        <div class="danger"><span>失败</span><strong>{{ changeSet.failed }}</strong></div>
        <div class="success"><span>已应用</span><strong>{{ changeSet.applied }}</strong></div>
      </div>

      <el-alert
        v-if="changeSet.changed === 0 && changeSet.state === 'previewed'"
        type="info"
        title="没有文件需要修改"
        description="操作没有命中，或生成的内容与现有 Caption 相同。"
        :closable="false"
        show-icon
      />
      <el-alert
        v-for="warning in preview.warnings || []"
        :key="warning"
        type="warning"
        :title="warning"
        :closable="false"
        show-icon
      />
      <el-alert
        v-if="changeSet.conflicts > 0"
        type="warning"
        title="存在外部修改冲突"
        description="冲突文件不会被静默覆盖；应用后可在变更集详情中查看。"
        :closable="false"
        show-icon
      />

      <section class="diff-section" aria-labelledby="diff-title">
        <div class="diff-heading">
          <div>
            <span>有界样本</span>
            <h3 id="diff-title">前后对比</h3>
          </div>
          <span>展示 {{ preview.diffs.length }} 项</span>
        </div>

        <div v-if="preview.diffs.length" class="diff-list">
          <article v-for="diff in preview.diffs" :key="diff.itemId" class="diff-item">
            <header>
              <strong>{{ diff.name }}</strong>
              <span :title="diff.relativePath">{{ diff.relativePath }}</span>
            </header>
            <div class="diff-columns">
              <div>
                <span>修改前</span>
                <pre :class="{ empty: !diff.before }">{{ diff.before || '无内容' }}</pre>
                <small v-if="diff.beforeTruncated">正文较长，此处仅展示前 4,000 个字符</small>
              </div>
              <div class="after">
                <span>修改后</span>
                <pre :class="{ empty: !diff.after }">{{ diff.after || '空结果' }}</pre>
                <small v-if="diff.afterTruncated">正文较长，此处仅展示前 4,000 个字符</small>
              </div>
            </div>
          </article>
        </div>
        <el-empty v-else description="没有可展示的差异" :image-size="72" />
      </section>

      <section v-if="preview.issues.length" class="issue-section" aria-labelledby="issue-title">
        <div class="diff-heading">
          <div>
            <span>不会写入</span>
            <h3 id="issue-title">冲突项目样本</h3>
          </div>
          <span>展示 {{ preview.issues.length }} 项</span>
        </div>
        <ul>
          <li v-for="issue in preview.issues" :key="issue.itemId">
            <div>
              <strong>{{ issue.name }}</strong>
              <span :title="issue.relativePath">{{ issue.relativePath }}</span>
            </div>
            <span>{{ issue.error }}</span>
          </li>
        </ul>
      </section>

      <section
        v-if="resultsLoading || (results && results.length)"
        v-loading="resultsLoading"
        class="result-section"
        aria-labelledby="result-title"
      >
        <div class="diff-heading">
          <div>
            <span>批次结果</span>
            <h3 id="result-title">逐项写入状态</h3>
          </div>
          <span>显示 {{ results?.length || 0 }} / {{ resultsTotal || 0 }} 项</span>
        </div>
        <ul v-if="results?.length">
          <li v-for="result in results" :key="result.itemId">
            <span :title="result.relativePath">{{ result.relativePath }}</span>
            <span v-if="result.error" class="result-error" :title="result.error">{{ result.error }}</span>
            <el-tag :type="resultType(result.state)">{{ RESULT_LABEL[result.state] }}</el-tag>
          </li>
        </ul>
      </section>

      <el-alert
        v-if="resultsError"
        type="error"
        title="无法读取逐项执行结果"
        :description="resultsError"
        :closable="false"
        show-icon
      />

      <div v-if="isRunning" class="running-state" role="status" aria-live="polite">
        <el-icon class="is-loading"><RefreshRight /></el-icon>
        <div>
          <strong>{{ STATE_LABEL[changeSet.state] }}</strong>
          <span>已应用 {{ changeSet.applied }} / {{ changeSet.changed }} 项</span>
        </div>
        <el-button text :loading="refreshing" @click="emit('refresh')">刷新状态</el-button>
      </div>

      <label v-if="changeSet.state === 'previewed' && !readonly" class="backup-option">
        <span>
          <strong>备份已有 Caption</strong>
          <small>写入前为现有 sidecar 创建批次备份和 manifest。</small>
        </span>
        <el-switch v-model="backupExisting" />
      </label>
      <el-alert
        v-if="changeSet.state === 'previewed' && !readonly && !backupExisting"
        class="backup-warning"
        type="warning"
        title="已关闭已有文件备份"
        description="本批次仍会写入文件，但已有 sidecar 无法通过本批次自动回滚；新建 sidecar 仍可在回滚时移除。"
        :closable="false"
        show-icon
      />
    </div>

    <template #footer>
      <div class="preview-footer">
        <span v-if="changeSet?.state === 'previewed'">
          <el-icon><WarningFilled /></el-icon> 应用时会重新核对扫描 revision 与文件指纹
        </span>
        <span v-else-if="changeSet?.state === 'completed'">
          <el-icon><Check /></el-icon> 变更已完成，可从历史记录发起回滚
        </span>
        <span v-else />
        <div>
          <el-button :disabled="applying" @click="visible = false">
            {{ changeSet?.state === 'previewed' ? '返回检查' : '关闭' }}
          </el-button>
          <el-button
            v-if="changeSet?.state === 'previewed' && !readonly"
            type="primary"
            :loading="applying"
            :disabled="!canApply"
            @click="emit('apply', backupExisting)"
          >
            确认应用 {{ changeSet.changed }} 项
          </el-button>
        </div>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
.preview-content {
  display: grid;
  gap: 16px;
}

.preview-header,
.preview-title,
.diff-heading,
.preview-footer,
.preview-footer > div,
.running-state,
.backup-option {
  display: flex;
  align-items: center;
  gap: 10px;
}

.preview-header,
.diff-heading,
.preview-footer,
.backup-option {
  justify-content: space-between;
}

.preview-icon {
  width: 38px;
  height: 38px;
  display: grid;
  place-items: center;
  border-radius: 8px;
  background: var(--brand-soft);
  color: var(--brand-strong);
  font-size: 20px;
}

.preview-title > div {
  display: grid;
  gap: 2px;
}

.preview-title span,
.diff-heading span,
.preview-footer > span,
.running-state span {
  color: var(--text-muted);
  font-size: 12px;
}

.preview-title strong {
  color: var(--text-strong);
  font-size: 17px;
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  background: var(--surface-sunken);
}

.stat-grid > div {
  min-width: 0;
  display: grid;
  gap: 2px;
  padding: 11px 12px;
  border-right: 1px solid var(--border-subtle);
}

.stat-grid > div:last-child {
  border-right: 0;
}

.stat-grid span {
  color: var(--text-muted);
  font-size: 12px;
}

.stat-grid strong {
  color: var(--text-strong);
  font-size: 20px;
}

.stat-grid .changed strong {
  color: var(--brand-strong);
}

.stat-grid .warning strong {
  color: var(--warning);
}

.stat-grid .danger strong {
  color: var(--danger);
}

.stat-grid .success strong {
  color: var(--success);
}

.diff-section,
.issue-section,
.result-section {
  display: grid;
  gap: 10px;
}

.diff-heading h3 {
  margin: 2px 0 0;
  color: var(--text-strong);
  font-size: 16px;
}

.diff-list {
  max-height: min(52vh, 560px);
  display: grid;
  gap: 10px;
  overflow: auto;
  padding-right: 3px;
}

.diff-item {
  overflow: hidden;
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
}

.diff-item > header {
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 10px;
  border-bottom: 1px solid var(--border-subtle);
  background: var(--surface-sunken);
}

.diff-item header strong,
.diff-item header span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.diff-item header strong {
  color: var(--text-strong);
  font-size: 13px;
}

.diff-item header span {
  color: var(--text-muted);
  font-size: 12px;
}

.diff-columns {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.diff-columns > div {
  min-width: 0;
  padding: 9px 10px 11px;
}

.diff-columns > div + div {
  border-left: 1px solid var(--border-subtle);
}

.diff-columns > div > span {
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 650;
}

.diff-columns pre {
  min-height: 62px;
  max-height: 180px;
  margin: 6px 0 0;
  overflow: auto;
  color: var(--text-secondary);
  font-family: var(--font-sans);
  font-size: 13px;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-word;
}

.diff-columns .after {
  background: color-mix(in srgb, var(--success-soft) 46%, transparent);
}

.diff-columns pre.empty {
  color: var(--text-muted);
  font-style: italic;
}

.diff-columns small {
  display: block;
  margin-top: 5px;
  color: var(--warning);
  font-size: 12px;
}

.issue-section ul {
  max-height: 220px;
  margin: 0;
  padding: 0;
  display: grid;
  overflow: auto;
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  list-style: none;
}

.issue-section li {
  min-width: 0;
  display: grid;
  grid-template-columns: minmax(160px, 0.8fr) minmax(220px, 1.2fr);
  gap: 12px;
  padding: 9px 10px;
  border-bottom: 1px solid var(--border-subtle);
  font-size: 12px;
}

.issue-section li:last-child {
  border-bottom: 0;
}

.issue-section li > div {
  min-width: 0;
  display: grid;
  gap: 2px;
}

.issue-section li strong,
.issue-section li span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.issue-section li > span {
  color: var(--warning);
}

.issue-section li div span {
  color: var(--text-muted);
}

.result-section ul {
  max-height: 260px;
  margin: 0;
  padding: 0;
  overflow: auto;
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  list-style: none;
}

.result-section li {
  min-width: 0;
  display: grid;
  grid-template-columns: minmax(180px, 1fr) minmax(160px, 0.8fr) auto;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-bottom: 1px solid var(--border-subtle);
  color: var(--text-secondary);
  font-size: 12px;
}

.result-section li:last-child {
  border-bottom: 0;
}

.result-section li > span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.result-section .result-error {
  color: var(--danger);
}

.running-state,
.backup-option {
  padding: 11px 12px;
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  background: var(--surface-sunken);
}

.running-state > .el-icon {
  color: var(--brand-strong);
  font-size: 22px;
}

.running-state > div,
.backup-option > span {
  display: grid;
  gap: 2px;
}

.running-state > div {
  min-width: 0;
  flex: 1;
}

.running-state strong,
.backup-option strong {
  color: var(--text-strong);
  font-size: 13px;
}

.backup-option small {
  color: var(--text-muted);
  font-size: 12px;
}

.preview-footer > span {
  display: flex;
  align-items: center;
  gap: 5px;
}

@media (max-width: 760px) {
  .stat-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .stat-grid > div:nth-child(3) {
    border-right: 0;
  }

  .stat-grid > div:nth-child(-n + 3) {
    border-bottom: 1px solid var(--border-subtle);
  }

  .diff-columns {
    grid-template-columns: 1fr;
  }

  .issue-section li {
    grid-template-columns: 1fr;
    gap: 4px;
  }

  .result-section li {
    grid-template-columns: minmax(0, 1fr) auto;
  }

  .result-section .result-error {
    grid-column: 1 / -1;
    grid-row: 2;
  }

  .diff-columns > div + div {
    border-top: 1px solid var(--border-subtle);
    border-left: 0;
  }

  .backup-option,
  .preview-footer {
    align-items: stretch;
    flex-direction: column;
  }

  .preview-footer > div {
    display: grid;
    grid-template-columns: 1fr 1fr;
  }
}
</style>
