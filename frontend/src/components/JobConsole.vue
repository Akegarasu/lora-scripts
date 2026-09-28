<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { Bottom, DocumentCopy, Loading, RefreshRight, Search, VideoPause, WarningFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

import type { JobStreamStatus } from '@/stores/jobs'

const props = defineProps<{
  lines: string[]
  streaming?: boolean
  connectionStatus?: JobStreamStatus
  streamError?: string
  lastEventAt?: string
}>()

const emit = defineEmits<{
  reconnect: []
}>()

const viewport = ref<HTMLElement | null>(null)
const follow = ref(true)
const query = ref('')
const wrapLines = ref(true)

const normalizedQuery = computed(() => query.value.trim().toLocaleLowerCase())
const visibleLines = computed(() => {
  if (!normalizedQuery.value) return props.lines
  return props.lines.filter((line) => line.toLocaleLowerCase().includes(normalizedQuery.value))
})
const isFiltered = computed(() => normalizedQuery.value.length > 0)
const visibleText = computed(() => visibleLines.value.join('\n'))
const effectiveStatus = computed<JobStreamStatus>(
  () => props.connectionStatus || (props.streaming ? 'live' : 'ended'),
)
const statusLabel = computed(() => {
  if (effectiveStatus.value === 'connecting') return '正在连接'
  if (effectiveStatus.value === 'live') return '实时输出'
  if (effectiveStatus.value === 'disconnected') return '连接已中断'
  return '日志已结束'
})
const lastEventLabel = computed(() => {
  if (!props.lastEventAt) return ''
  const value = new Date(props.lastEventAt)
  if (Number.isNaN(value.getTime())) return ''
  return `最近事件 ${value.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}`
})

function scrollToBottom() {
  const el = viewport.value
  if (!el) return
  el.scrollTop = el.scrollHeight
}

function toggleFollow() {
  follow.value = !follow.value
  if (follow.value) void nextTick(scrollToBottom)
}

async function toggleWrap() {
  wrapLines.value = !wrapLines.value
  if (!follow.value) return
  await nextTick()
  scrollToBottom()
}

function onScroll() {
  const el = viewport.value
  if (!el) return
  // Within 24px of the bottom counts as "following".
  follow.value = el.scrollHeight - el.scrollTop - el.clientHeight < 24
}

function clearFilter() {
  query.value = ''
}

async function copyVisibleLogs() {
  if (visibleLines.value.length === 0) return
  try {
    await navigator.clipboard.writeText(visibleText.value)
    ElMessage.success(isFiltered.value ? `已复制 ${visibleLines.value.length} 行筛选结果` : '日志已复制')
  } catch {
    ElMessage.error('复制失败，请检查浏览器的剪贴板权限')
  }
}

watch(
  visibleText,
  async () => {
    if (!follow.value) return
    await nextTick()
    scrollToBottom()
  },
  { immediate: true },
)
</script>

<template>
  <div class="console">
    <div class="console-bar">
      <div class="console-summary" aria-live="polite">
        <span class="console-status">
          <el-icon v-if="effectiveStatus === 'connecting'" class="spin"><Loading /></el-icon>
          <span
            v-else
            class="status-dot"
            :class="{ live: effectiveStatus === 'live', disconnected: effectiveStatus === 'disconnected' }"
            aria-hidden="true"
          />
          <span :title="lastEventLabel">{{ statusLabel }}</span>
        </span>
        <span class="line-count">
          {{ isFiltered ? `${visibleLines.length} / ${lines.length} 行` : `${lines.length} 行` }}
        </span>
        <span v-if="!follow" class="follow-paused">已暂停跟随</span>
      </div>

      <div class="console-actions">
        <el-input
          v-model="query"
          class="log-search"
          :prefix-icon="Search"
          placeholder="搜索日志"
          aria-label="搜索日志"
          clearable
          size="small"
        />
        <el-button
          v-if="effectiveStatus === 'disconnected'"
          class="console-action reconnect-action"
          size="small"
          text
          :icon="RefreshRight"
          @click="emit('reconnect')"
        >
          重新连接
        </el-button>
        <el-button
          v-if="isFiltered"
          class="console-action"
          size="small"
          text
          aria-label="清除日志筛选"
          @click="clearFilter"
        >
          清除筛选
        </el-button>
        <el-button
          class="console-action"
          size="small"
          text
          :icon="DocumentCopy"
          :disabled="visibleLines.length === 0"
          @click="copyVisibleLogs"
        >
          {{ isFiltered ? '复制结果' : '复制' }}
        </el-button>
        <el-button
          class="console-action"
          size="small"
          text
          :aria-pressed="wrapLines"
          @click="toggleWrap"
        >
          {{ wrapLines ? '不换行' : '自动换行' }}
        </el-button>
        <el-button
          class="console-action"
          size="small"
          text
          :icon="follow ? VideoPause : Bottom"
          :aria-pressed="!follow"
          @click="toggleFollow"
        >
          {{ follow ? '暂停跟随' : '回到底部' }}
        </el-button>
      </div>
    </div>
    <div v-if="streamError" class="console-notice" role="status">
      <el-icon aria-hidden="true"><WarningFilled /></el-icon>
      <span>{{ streamError }}</span>
      <button v-if="effectiveStatus === 'disconnected'" type="button" @click="emit('reconnect')">
        重新连接
      </button>
    </div>
    <div
      ref="viewport"
      class="console-body"
      :class="{ 'wrap-lines': wrapLines }"
      tabindex="0"
      aria-label="任务运行日志"
      @scroll="onScroll"
    >
      <div v-if="lines.length === 0" class="console-empty">
        <span class="empty-title">暂无日志输出</span>
        <span>{{ streaming ? '任务有新输出时会自动显示在这里' : '这个任务没有可显示的日志' }}</span>
      </div>
      <div v-else-if="visibleLines.length === 0" class="console-empty">
        <span class="empty-title">没有匹配的日志</span>
        <span>换一个关键词，或清除当前筛选。</span>
        <el-button class="empty-action" size="small" text @click="clearFilter">清除筛选</el-button>
      </div>
      <pre v-else class="console-text">{{ visibleText }}</pre>
    </div>
  </div>
</template>

<style scoped>
.console {
  container-name: job-console;
  container-type: inline-size;
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  border: 1px solid #293540;
  border-radius: 10px;
  overflow: hidden;
  background: #0b1117;
}

.console-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 44px;
  padding: 6px 8px 6px 12px;
  border-bottom: 1px solid #293540;
  background: #131c24;
  color: #aab6c2;
  font-size: 13.5px;
}

.console-summary,
.console-status {
  display: flex;
  align-items: center;
  gap: 6px;
}

.console-status {
  min-height: 26px;
  padding: 3px 8px;
  border: 1px solid #34414d;
  border-radius: 6px;
  background: #0b1117;
}

.console-summary {
  flex: 0 0 auto;
  white-space: nowrap;
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #647382;
}

.status-dot.live {
  background: #38bda8;
}

.status-dot.disconnected {
  background: #f4bd67;
}

.line-count {
  color: #71808e;
}

.line-count::before {
  margin-right: 6px;
  content: '·';
}

.follow-paused {
  padding: 3px 7px;
  border: 1px solid rgba(244, 189, 103, 0.28);
  border-radius: 5px;
  background: rgba(217, 119, 6, 0.16);
  color: #f4bd67;
}

.console-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 2px;
  min-width: 0;
}

.console-notice {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid rgba(244, 189, 103, 0.24);
  background: rgba(217, 119, 6, 0.12);
  color: #f0c47d;
  font-size: 13px;
}

.console-notice span {
  min-width: 0;
  flex: 1;
}

.console-notice button {
  flex: none;
  padding: 2px 0;
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  font-weight: 650;
  cursor: pointer;
}

.console-notice button:hover,
.console-notice button:focus-visible {
  text-decoration: underline;
  text-underline-offset: 3px;
}

.log-search {
  width: 210px;
}

.log-search :deep(.el-input__wrapper) {
  background: #0b1117;
  box-shadow: 0 0 0 1px #34414d inset;
}

.log-search :deep(.el-input__inner) {
  color: #dce5ed;
}

.log-search :deep(.el-input__inner::placeholder) {
  color: #657381;
}

.console-action {
  color: #aab6c2;
}

.console-action:hover,
.console-action:focus-visible {
  color: #f1f6fa;
  background: rgba(255, 255, 255, 0.07);
}

.spin {
  animation: console-spin 1s linear infinite;
}

@keyframes console-spin {
  to {
    transform: rotate(360deg);
  }
}

.console-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 12px 14px 18px;
  scrollbar-color: #34414d transparent;
}

.console-empty {
  display: grid;
  place-content: center;
  justify-items: center;
  min-height: 100%;
  color: #657482;
  font-size: 13px;
  text-align: center;
}

.empty-title {
  margin-bottom: 4px;
  color: #aab6c2;
  font-weight: 600;
}

.empty-action {
  margin-top: 6px;
  color: #67c7b8;
}

.console-text {
  margin: 0;
  color: #d9e2ea;
  font-family: 'Cascadia Code', 'SFMono-Regular', Consolas, 'Liberation Mono', monospace;
  font-size: 14px;
  line-height: 1.6;
  tab-size: 2;
  white-space: pre;
}

.console-body.wrap-lines .console-text {
  white-space: pre-line;
  overflow-wrap: anywhere;
}

@container job-console (max-width: 700px) {
  .console-bar {
    align-items: stretch;
    flex-direction: column;
    padding: 8px 10px;
  }

  .console-actions {
    justify-content: flex-start;
    flex-wrap: wrap;
  }

  .log-search {
    flex: 1 1 180px;
    width: auto;
  }
}

@container job-console (max-width: 460px) {
  .console-summary {
    flex-wrap: wrap;
  }

  .console-actions {
    gap: 0;
  }

  .log-search {
    flex-basis: 100%;
  }
}

@media (max-width: 720px) {
  .console-bar {
    padding: 8px 10px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .spin {
    animation: none;
  }
}
</style>
