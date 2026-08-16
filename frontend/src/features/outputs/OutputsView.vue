<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  ArrowUpBold,
  CopyDocument,
  Document,
  FolderOpened,
  Refresh,
  Search,
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

import { apiClient } from '@/api/client'
import type { FileItem } from '@/api/types'

interface DirectoryLocation {
  requestPath: string
  displayPath: string
  label: string
}

const ROOT_LABEL = '输出目录'
const ROOT_FALLBACK_PATH = 'output'

const items = ref<FileItem[]>([])
const locations = ref<DirectoryLocation[]>([
  {
    requestPath: '',
    displayPath: ROOT_FALLBACK_PATH,
    label: ROOT_LABEL,
  },
])
const query = ref('')
const loading = ref(false)
const error = ref('')
const activeFilter = ref<'all' | 'dir' | 'file'>('all')
let loadVersion = 0

const currentLocation = computed(() => locations.value[locations.value.length - 1])
const canGoUp = computed(() => locations.value.length > 1)
const directoryCount = computed(() => items.value.filter((item) => item.type === 'dir').length)
const fileCount = computed(() => items.value.filter((item) => item.type === 'file').length)
const totalFileBytes = computed(() =>
  items.value.reduce((total, item) => total + (item.type === 'file' ? item.size : 0), 0),
)
const normalizedQuery = computed(() => query.value.trim().toLocaleLowerCase())
const visibleItems = computed(() => {
  return items.value.filter((item) => {
    if (activeFilter.value !== 'all' && item.type !== activeFilter.value) return false
    if (!normalizedQuery.value) return true
    const extension = item.type === 'file' ? fileExtension(item.name) : '文件夹'
    return [item.name, extension].join(' ').toLocaleLowerCase().includes(normalizedQuery.value)
  })
})
const resultLabel = computed(() => {
  if (!normalizedQuery.value) return `当前目录共 ${items.value.length} 项`
  return `找到 ${visibleItems.value.length} 项，共 ${items.value.length} 项`
})

function parentPath(value: string) {
  const normalized = value.replace(/\\/g, '/').replace(/\/+$/, '')
  const separator = normalized.lastIndexOf('/')
  if (separator < 0) return ''
  if (separator === 0) return '/'
  if (separator === 2 && normalized[1] === ':') return `${normalized.slice(0, 2)}/`
  return normalized.slice(0, separator)
}

function updateResolvedRoot(entries: FileItem[]) {
  if (locations.value.length !== 1 || currentLocation.value.requestPath || entries.length === 0) return
  const resolvedRoot = parentPath(entries[0].path)
  if (!resolvedRoot) return
  locations.value[0] = {
    ...locations.value[0],
    displayPath: resolvedRoot,
  }
}

async function loadDirectory(requestPath: string) {
  const requestVersion = ++loadVersion
  loading.value = true
  error.value = ''

  try {
    const response = await apiClient.browseFiles({
      kind: 'file',
      root: 'output',
      path: requestPath,
    })
    if (requestVersion !== loadVersion) return false
    items.value = response.items
    updateResolvedRoot(response.items)
    return true
  } catch (reason) {
    if (requestVersion === loadVersion) {
      error.value = reason instanceof Error ? reason.message : String(reason)
    }
    return false
  } finally {
    if (requestVersion === loadVersion) loading.value = false
  }
}

async function enterDirectory(item: FileItem) {
  if (loading.value || item.type !== 'dir') return
  const loaded = await loadDirectory(item.path)
  if (!loaded) return
  locations.value.push({
    requestPath: item.path,
    displayPath: item.path,
    label: item.name,
  })
  query.value = ''
}

async function goUp() {
  if (loading.value || !canGoUp.value) return
  const parent = locations.value[locations.value.length - 2]
  const loaded = await loadDirectory(parent.requestPath)
  if (!loaded) return
  locations.value.pop()
  query.value = ''
}

function refresh() {
  void loadDirectory(currentLocation.value.requestPath)
}

function clearSearch() {
  query.value = ''
}

function fileExtension(name: string) {
  const separator = name.lastIndexOf('.')
  if (separator <= 0 || separator === name.length - 1) return '无扩展名'
  return name.slice(separator + 1).toLocaleUpperCase()
}

function itemKind(item: FileItem) {
  return item.type === 'dir' ? '文件夹' : fileExtension(item.name)
}

function formatSize(value: number) {
  if (!Number.isFinite(value) || value <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const unitIndex = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1)
  const amount = value / 1024 ** unitIndex
  const precision = unitIndex === 0 || amount >= 100 ? 0 : amount >= 10 ? 1 : 2
  return `${amount.toFixed(precision)} ${units[unitIndex]}`
}

async function copyPath(path: string, label: string) {
  if (!path) return
  try {
    await navigator.clipboard.writeText(path)
    ElMessage.success(`已复制${label}路径`)
  } catch {
    ElMessage.error('复制失败，请检查浏览器的剪贴板权限')
  }
}

onMounted(() => {
  void loadDirectory('')
})
</script>

<template>
  <section class="outputs-page" aria-labelledby="outputs-title">
    <header class="page-header">
      <div class="page-heading">
        <h1 id="outputs-title">训练产物</h1>
      </div>

      <div class="header-actions">
        <el-input
          v-model="query"
          class="header-search"
          :prefix-icon="Search"
          :disabled="items.length === 0"
          placeholder="搜索"
          aria-label="搜索当前输出目录"
          clearable
        />
        <el-button
          text
          :icon="CopyDocument"
          :disabled="!currentLocation.displayPath"
          @click="copyPath(currentLocation.displayPath, '当前目录')"
        >
          复制路径
        </el-button>
        <el-button text :icon="Refresh" :loading="loading" @click="refresh">刷新</el-button>
      </div>
    </header>

    <div class="view-toolbar">
      <div class="filter-tabs" role="group" aria-label="产物类型">
        <button type="button" :class="{ active: activeFilter === 'all' }" @click="activeFilter = 'all'">全部</button>
        <button type="button" :class="{ active: activeFilter === 'dir' }" @click="activeFilter = 'dir'">文件夹</button>
        <button type="button" :class="{ active: activeFilter === 'file' }" @click="activeFilter = 'file'">文件</button>
      </div>
    </div>

    <section class="browser-panel" aria-label="输出文件浏览器">
      <div class="location-bar">
        <el-button
          :icon="ArrowUpBold"
          :disabled="!canGoUp || loading"
          aria-label="返回上级输出目录"
          @click="goUp"
        >
          上级
        </el-button>

        <div class="current-location" aria-live="polite">
          <span>{{ currentLocation.label }}</span>
          <code :title="currentLocation.displayPath">{{ currentLocation.displayPath }}</code>
        </div>

        <el-button
          circle
          text
          :icon="CopyDocument"
          :disabled="!currentLocation.displayPath"
          aria-label="复制当前目录路径"
          title="复制当前目录路径"
          @click="copyPath(currentLocation.displayPath, '当前目录')"
        />
      </div>

      <div class="browser-toolbar">
        <div class="directory-stats" aria-label="当前目录统计">
          <span><strong>{{ directoryCount }}</strong> 个文件夹</span>
          <span><strong>{{ fileCount }}</strong> 个文件</span>
          <span v-if="fileCount"><strong>{{ formatSize(totalFileBytes) }}</strong> 文件总量</span>
        </div>

        <span class="result-count" aria-live="polite">{{ resultLabel }}</span>
      </div>

      <el-alert
        v-if="error && items.length > 0"
        class="inline-error"
        type="error"
        :title="error"
        description="当前仍显示上一次成功读取的结果。"
        show-icon
        :closable="false"
      >
        <template #default>
          <el-button size="small" @click="refresh">重试</el-button>
        </template>
      </el-alert>

      <div
        class="file-list"
        :class="{ refreshing: loading && items.length > 0 }"
        role="list"
        :aria-busy="loading"
        aria-label="当前目录内容"
      >
        <div class="list-heading" aria-hidden="true">
          <span>名称与路径</span>
          <span>类型</span>
          <span>大小</span>
          <span>操作</span>
        </div>

        <div v-if="loading && items.length === 0" class="skeleton-list" role="status">
          <span class="sr-only">正在读取输出目录</span>
          <div v-for="index in 6" :key="index" class="skeleton-row">
            <el-skeleton animated>
              <template #template>
                <el-skeleton-item variant="circle" class="skeleton-icon" />
                <div class="skeleton-copy">
                  <el-skeleton-item variant="text" class="skeleton-name" />
                  <el-skeleton-item variant="text" class="skeleton-path" />
                </div>
                <el-skeleton-item variant="text" class="skeleton-meta" />
              </template>
            </el-skeleton>
          </div>
        </div>

        <div v-else-if="error && items.length === 0" class="state-panel error-state" role="alert">
          <span class="state-icon error" aria-hidden="true">!</span>
          <div>
            <strong>无法读取输出目录</strong>
            <p>{{ error }}</p>
          </div>
          <el-button :icon="Refresh" :loading="loading" @click="refresh">重新读取</el-button>
        </div>

        <div v-else-if="items.length === 0" class="state-panel">
          <span class="state-icon" aria-hidden="true"><el-icon><FolderOpened /></el-icon></span>
          <div>
            <strong>当前目录还没有输出文件</strong>
          </div>
          <el-button :icon="Refresh" :loading="loading" @click="refresh">刷新目录</el-button>
        </div>

        <div v-else-if="visibleItems.length === 0" class="state-panel">
          <span class="state-icon" aria-hidden="true"><el-icon><Search /></el-icon></span>
          <div>
            <strong>没有匹配的项目</strong>
          </div>
          <el-button @click="clearSearch">清除搜索</el-button>
        </div>

        <article
          v-for="item in visibleItems"
          v-else
          :key="item.path"
          class="file-row"
          :class="{ directory: item.type === 'dir' }"
          role="listitem"
        >
          <span class="file-icon" :class="{ folder: item.type === 'dir' }" aria-hidden="true">
            <el-icon>
              <FolderOpened v-if="item.type === 'dir'" />
              <Document v-else />
            </el-icon>
          </span>

          <button
            v-if="item.type === 'dir'"
            class="item-primary directory-link"
            type="button"
            :aria-label="`打开文件夹 ${item.name}`"
            @click="enterDirectory(item)"
          >
            <strong>{{ item.name }}</strong>
            <code :title="item.path">{{ item.path }}</code>
          </button>
          <div v-else class="item-primary">
            <strong>{{ item.name }}</strong>
            <code :title="item.path">{{ item.path }}</code>
          </div>

          <span class="item-kind" :class="{ folder: item.type === 'dir' }">{{ itemKind(item) }}</span>
          <span class="item-size">{{ item.type === 'dir' ? '—' : formatSize(item.size) }}</span>

          <el-button
            class="copy-action"
            circle
            text
            :icon="CopyDocument"
            :aria-label="`复制${item.type === 'dir' ? '文件夹' : '文件'} ${item.name} 的路径`"
            title="复制路径"
            @click="copyPath(item.path, item.type === 'dir' ? '文件夹' : '文件')"
          />
        </article>
      </div>
    </section>
  </section>
</template>

<style scoped>
.outputs-page {
  width: min(100%, 1380px);
  min-height: 100dvh;
  margin: 0 auto;
  padding: 36px clamp(20px, 3vw, 48px) 64px;
  color: var(--text);
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
}

.page-heading {
  min-width: 0;
}

.eyebrow {
  display: block;
  margin-bottom: 7px;
  color: var(--brand-strong);
  font-size: var(--font-caption);
  font-weight: 720;
  letter-spacing: 0.1em;
}

.page-heading h1 {
  margin: 0;
  color: var(--text-strong);
  font-family: var(--font-display);
  font-size: var(--font-page-title);
  line-height: 1.15;
  font-weight: 730;
  letter-spacing: -0.035em;
}

.page-heading p {
  max-width: 58ch;
  margin: 8px 0 0;
  color: var(--text-secondary);
  font-size: 14px;
  line-height: 1.5;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.header-search {
  width: min(32vw, 300px);
  margin-right: 8px;
}

.header-search :deep(.el-input__wrapper) {
  min-height: 38px;
  border-radius: 999px;
}

.header-actions :deep(.el-button) {
  border: 0;
  background: transparent;
}

.header-actions :deep(.el-button:hover) {
  background: var(--surface-hover);
}

.view-toolbar {
  min-height: 58px;
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 18px;
  margin-top: 34px;
}

.filter-tabs {
  display: flex;
  gap: 4px;
}

.filter-tabs button {
  min-height: 36px;
  padding: 7px 17px;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: var(--text-secondary);
  font: inherit;
  font-size: 13px;
  cursor: pointer;
}

.filter-tabs button:hover,
.filter-tabs button.active {
  background: var(--surface-hover);
  color: var(--text-strong);
}

.browser-panel {
  margin-top: 4px;
  overflow: visible;
  border: 0;
  border-radius: 0;
  background: transparent;
}

.location-bar {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  padding: 10px 0;
  border-bottom: 1px solid var(--border-subtle);
  background: transparent;
}

.current-location {
  min-width: 0;
  display: grid;
  gap: 2px;
}

.current-location > span {
  color: var(--text-strong);
  font-size: 13px;
  font-weight: 650;
}

.current-location code {
  overflow: hidden;
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.browser-toolbar {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 10px 0;
  border-bottom: 1px solid var(--border-subtle);
}

.directory-stats {
  min-width: 0;
  display: flex;
  align-items: center;
  flex: 1;
  flex-wrap: wrap;
  gap: 7px 18px;
  color: var(--text-muted);
  font-size: 12px;
}

.directory-stats strong {
  color: var(--text-secondary);
  font-weight: 680;
}

.result-count {
  color: var(--text-muted);
  font-size: 12px;
  white-space: nowrap;
}

.inline-error {
  margin: 12px 14px 0;
}

.file-list {
  min-height: 360px;
  padding: 0;
  transition: opacity 120ms ease;
}

.file-list.refreshing {
  opacity: 0.58;
  pointer-events: none;
}

.list-heading,
.file-row {
  display: grid;
  align-items: center;
  gap: 12px;
}

.list-heading {
  grid-template-columns: 38px minmax(242px, 1fr) 116px 100px 48px;
  min-height: 46px;
  border-bottom: 1px solid var(--border-subtle);
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 620;
}

.list-heading span:first-child {
  grid-column: 1 / 3;
}

.list-heading span:nth-child(2),
.list-heading span:nth-child(3),
.list-heading span:nth-child(4) {
  text-align: right;
}

.file-row {
  position: relative;
  grid-template-columns: 38px minmax(242px, 1fr) 116px 100px 48px;
  min-height: 62px;
  padding: 0 6px;
  border-radius: 8px;
  border-bottom: 1px solid var(--border-subtle);
}

.file-row:last-child {
  border-bottom: 0;
}

.file-row:hover {
  background: var(--surface-hover);
}

.file-icon {
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  border: 0;
  border-radius: 0;
  background: transparent;
  color: var(--text-muted);
  font-size: 17px;
}

.file-icon.folder {
  color: var(--brand-strong);
}

.item-primary {
  min-width: 0;
  display: grid;
  gap: 4px;
  padding: 10px 0;
}

.item-primary strong {
  overflow: hidden;
  color: var(--text-strong);
  font-size: 14px;
  line-height: 1.3;
  font-weight: 640;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.item-primary code {
  overflow: hidden;
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.directory-link {
  width: 100%;
  border: 0;
  background: transparent;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.directory-link:hover strong {
  color: var(--brand-strong);
}

.directory-link:focus-visible {
  border-radius: 5px;
  outline-offset: 3px;
}

.item-kind,
.item-size {
  justify-self: end;
  color: var(--text-secondary);
  font-size: 12px;
  white-space: nowrap;
}

.item-kind {
  max-width: 110px;
  overflow: hidden;
  padding: 3px 7px;
  border: 0;
  border-radius: 0;
  background: transparent;
  text-overflow: ellipsis;
}

.item-kind.folder {
  color: var(--brand-strong);
}

.item-size {
  font-family: var(--font-mono);
}

.copy-action {
  justify-self: end;
}

.skeleton-list {
  display: grid;
}

.skeleton-row {
  min-height: 68px;
  display: grid;
  align-items: center;
  border-bottom: 1px solid var(--border-subtle);
}

.skeleton-row :deep(.el-skeleton__template) {
  display: grid;
  grid-template-columns: 38px minmax(0, 1fr) 90px;
  align-items: center;
  gap: 12px;
}

.skeleton-icon {
  width: 32px;
  height: 32px;
}

.skeleton-copy {
  min-width: 0;
  display: grid;
  gap: 7px;
}

.skeleton-name {
  width: min(220px, 60%);
}

.skeleton-path {
  width: min(480px, 86%);
}

.skeleton-meta {
  justify-self: end;
  width: 72px;
}

.state-panel {
  min-height: 320px;
  display: grid;
  grid-template-columns: auto minmax(0, 420px) auto;
  place-content: center;
  align-items: center;
  gap: 14px;
  padding: 36px 18px;
  color: var(--text-secondary);
}

.state-icon {
  width: 42px;
  height: 42px;
  display: grid;
  place-items: center;
  border: 0;
  border-radius: 50%;
  background: var(--surface-sunken);
  color: var(--text-muted);
  font-size: 19px;
  font-weight: 700;
}

.state-icon.error {
  background: var(--danger-soft);
  color: var(--danger);
}

.state-panel strong {
  color: var(--text-strong);
  font-size: 15px;
  font-weight: 660;
}

.state-panel p {
  margin: 4px 0 0;
  color: var(--text-muted);
  font-size: 13px;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  clip-path: inset(50%);
  white-space: nowrap;
}

@media (max-width: 900px) {
  .list-heading {
    grid-template-columns: 36px minmax(214px, 1fr) 96px 80px 40px;
  }

  .file-row {
    grid-template-columns: 36px minmax(214px, 1fr) 96px 80px 40px;
  }
}

@media (max-width: 720px) {
  .outputs-page {
    padding: 24px 14px 92px;
  }

  .page-header {
    align-items: flex-start;
    flex-direction: column;
    gap: 16px;
  }

  .header-actions {
    width: 100%;
    flex-wrap: wrap;
  }

  .header-search {
    width: 100%;
    margin: 0 0 4px;
  }

  .view-toolbar {
    min-height: 48px;
    margin-top: 20px;
  }

  .browser-panel {
    margin-top: 10px;
  }

  .browser-toolbar {
    align-items: flex-start;
    flex-direction: column;
    gap: 10px;
    padding: 10px 0;
  }

  .result-count {
    justify-self: start;
  }

  .file-list {
    min-height: 320px;
    padding: 0;
  }

  .list-heading {
    display: none;
  }

  .file-row {
    grid-template-columns: 34px minmax(0, 1fr) 40px;
    gap: 9px;
    min-height: 82px;
    padding: 8px 0;
  }

  .item-primary {
    padding: 2px 0;
  }

  .item-kind,
  .item-size {
    grid-column: 2;
    grid-row: 2;
  }

  .item-kind {
    max-width: calc(100% - 86px);
    justify-self: start;
  }

  .item-size {
    justify-self: end;
  }

  .copy-action {
    grid-column: 3;
    grid-row: 1 / 3;
  }

  .state-panel {
    min-height: 300px;
    grid-template-columns: minmax(0, 1fr);
    justify-items: center;
    text-align: center;
  }
}

@media (max-width: 460px) {
  .location-bar {
    grid-template-columns: auto minmax(0, 1fr) auto;
    padding: 10px;
  }

  .location-bar > :deep(.el-button:first-child) {
    padding-inline: 10px;
  }

  .directory-stats {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 6px 12px;
  }

  .directory-stats span:last-child {
    grid-column: 1 / -1;
  }
}

@media (prefers-reduced-motion: reduce) {
  .file-list {
    transition: none;
  }
}
</style>
