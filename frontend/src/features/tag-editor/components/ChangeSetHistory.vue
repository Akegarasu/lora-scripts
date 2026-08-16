<script setup lang="ts">
import { Clock, RefreshRight, RefreshLeft } from '@element-plus/icons-vue'

import type { TagEditorChangeSetSummary, TagEditorChangeState } from '@/api/types'

defineProps<{
  changes: TagEditorChangeSetSummary[]
  loading: boolean
  error?: string
  rollbackId: string
}>()

const emit = defineEmits<{
  refresh: []
  details: [changeSet: TagEditorChangeSetSummary]
  rollback: [changeSet: TagEditorChangeSetSummary]
}>()

const STATE_LABEL: Record<TagEditorChangeState, string> = {
  previewed: '待确认',
  queued: '已排队',
  applying: '应用中',
  completed: '已完成',
  partial: '部分完成',
  failed: '失败',
  rolling_back: '回滚中',
  rolled_back: '已回滚',
  rollback_partial: '部分回滚',
  interrupted: '已中断',
}

function stateType(state: TagEditorChangeState) {
  if (state === 'completed' || state === 'rolled_back') return 'success'
  if (state === 'partial' || state === 'rollback_partial' || state === 'previewed') return 'warning'
  if (state === 'failed') return 'danger'
  return 'info'
}

function formatTime(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}
</script>

<template>
  <section class="change-history" aria-labelledby="change-history-title">
    <header>
      <div>
        <h2 id="change-history-title">最近变更</h2>
      </div>
      <el-button
        circle
        text
        :icon="RefreshRight"
        :loading="loading"
        aria-label="刷新变更记录"
        @click="emit('refresh')"
      />
    </header>

    <el-alert
      v-if="error"
      type="error"
      title="无法读取变更记录"
      :description="error"
      :closable="false"
      show-icon
    />

    <div v-if="changes.length" class="change-list">
      <article v-for="change in changes" :key="change.id" class="change-item">
        <div class="change-title">
          <span class="change-icon"><el-icon><Clock /></el-icon></span>
          <div>
            <strong :title="change.datasetPath || change.id">{{ change.datasetPath || change.id }}</strong>
            <span>{{ formatTime(change.endedAt || change.startedAt || change.createdAt) }}</span>
          </div>
          <el-tag :type="stateType(change.state)">{{ STATE_LABEL[change.state] }}</el-tag>
        </div>
        <div class="change-stats">
          <span>修改 {{ change.changed }}</span>
          <span>应用 {{ change.applied }}</span>
          <span v-if="change.conflicts" class="warning">冲突 {{ change.conflicts }}</span>
          <span v-if="change.failed" class="danger">失败 {{ change.failed }}</span>
        </div>
        <div class="change-actions">
          <el-button text size="small" @click="emit('details', change)">查看状态</el-button>
          <el-button
            v-if="change.canRollback && ['completed', 'partial', 'rollback_partial'].includes(change.state)"
            text
            size="small"
            type="warning"
            :icon="RefreshLeft"
            :loading="rollbackId === change.id"
            @click="emit('rollback', change)"
          >
            回滚
          </el-button>
        </div>
      </article>
    </div>

    <div v-else-if="!loading && !error" class="history-empty">
      <el-icon><Clock /></el-icon>
      <strong>还没有变更记录</strong>
    </div>
  </section>
</template>

<style scoped>
.change-history {
  display: grid;
  gap: 12px;
  padding: 16px;
  border-top: 1px solid var(--border-subtle);
}

.change-history > header,
.change-title,
.change-stats,
.change-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.change-history > header {
  justify-content: space-between;
}

.change-history > header > div {
  display: grid;
  gap: 2px;
}

.change-history > header span {
  color: var(--brand-strong);
  font-size: 12px;
  font-weight: 700;
}

.change-history h2 {
  margin: 0;
  color: var(--text-strong);
  font-size: 16px;
}

.change-list {
  display: grid;
  gap: 7px;
}

.change-item {
  display: grid;
  gap: 8px;
  padding: 9px;
  border: 0;
  border-radius: 8px;
  background: var(--surface-sunken);
}

.change-title {
  min-width: 0;
}

.change-title > div {
  min-width: 0;
  flex: 1;
  display: grid;
  gap: 1px;
}

.change-title strong {
  overflow: hidden;
  color: var(--text-strong);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.change-title span,
.change-stats span {
  color: var(--text-muted);
  font-size: 11px;
}

.change-icon {
  flex: 0 0 29px;
  width: 29px;
  height: 29px;
  display: grid;
  place-items: center;
  border-radius: 7px;
  background: var(--surface);
  color: var(--brand-strong);
}

.change-stats {
  flex-wrap: wrap;
}

.change-stats .warning {
  color: var(--warning);
}

.change-stats .danger {
  color: var(--danger);
}

.change-actions {
  justify-content: flex-end;
  padding-top: 2px;
}

.history-empty {
  min-height: 140px;
  display: grid;
  place-items: center;
  align-content: center;
  gap: 6px;
  color: var(--text-muted);
  text-align: center;
}

.history-empty .el-icon {
  font-size: 26px;
}

.history-empty strong {
  color: var(--text-strong);
  font-size: 13px;
}

</style>
