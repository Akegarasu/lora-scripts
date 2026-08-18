<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  ArrowDownBold,
  ArrowRightBold,
  ArrowUpBold,
  CopyDocument,
  Document,
  FolderOpened,
  InfoFilled,
  Picture,
  Refresh,
  Search,
  View as ViewIcon,
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

import { apiClient, outputFileUrl } from '@/api/client'
import type { FileItem, FileManagerCapability, SafetensorsMetadataResponse } from '@/api/types'

interface DirectoryLocation {
  requestPath: string
  displayPath: string
  label: string
}

interface ItemEntry {
  kind: 'item'
  item: FileItem
}

interface ArtifactGroup {
  kind: 'group'
  key: string
  primary: FileItem
  checkpoints: FileItem[]
  hasFinal: boolean
}

type BrowserEntry = ItemEntry | ArtifactGroup
type ItemFilter = 'all' | 'dir' | 'file'

const ROOT_LABEL = '输出目录'
const ROOT_FALLBACK_PATH = 'output'
const AUTOSAVE_PATTERN = /^(.*)-(\d{6})\.(safetensors|ckpt|pt|pth)$/i
const IMAGE_EXTENSIONS = new Set(['jpg', 'jpeg', 'png', 'webp', 'bmp', 'gif', 'avif'])
const IMPORTANT_METADATA_KEYS = [
  'modelspec.title',
  'ss_output_name',
  'ss_base_model_version',
  'ss_sd_model_name',
  'ss_network_module',
  'ss_network_dim',
  'ss_network_alpha',
  'ss_epoch',
  'ss_num_epochs',
  'ss_steps',
  'ss_max_train_steps',
  'ss_resolution',
  'ss_optimizer',
  'ss_lr_scheduler',
  'ss_unet_lr',
  'ss_text_encoder_lr',
  'sshs_model_hash',
  'sshs_legacy_hash',
]
const metadataPriority = new Map(IMPORTANT_METADATA_KEYS.map((key, index) => [key, index]))

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
const activeFilter = ref<ItemFilter>('all')
const expandedGroups = ref(new Set<string>())
const fileManagerCapability = ref<FileManagerCapability | null>(null)
const revealingPaths = ref(new Set<string>())

const imagePreviewOpen = ref(false)
const imagePreviewItem = ref<FileItem | null>(null)
const imageLoadFailed = ref(false)

const metadataOpen = ref(false)
const metadataItem = ref<FileItem | null>(null)
const metadata = ref<SafetensorsMetadataResponse | null>(null)
const metadataLoading = ref(false)
const metadataError = ref('')
const metadataQuery = ref('')

let loadVersion = 0
let metadataLoadVersion = 0

const currentLocation = computed(() => locations.value[locations.value.length - 1])
const canGoUp = computed(() => locations.value.length > 1)
const directoryCount = computed(() => items.value.filter((item) => item.type === 'dir').length)
const fileCount = computed(() => items.value.filter((item) => item.type === 'file').length)
const totalFileBytes = computed(() =>
  items.value.reduce((total, item) => total + (item.type === 'file' ? item.size : 0), 0),
)
const normalizedQuery = computed(() => query.value.trim().toLocaleLowerCase())
const canRevealInFileManager = computed(() => fileManagerCapability.value?.available === true)
const fileManagerUnavailableReason = computed(
  () => fileManagerCapability.value?.reason || '当前运行环境无法调用图形化文件管理器',
)

const browserEntries = computed<BrowserEntry[]>(() => {
  const directories = items.value
    .filter((item) => item.type === 'dir')
    .map<ItemEntry>((item) => ({ kind: 'item', item }))
  const files = items.value.filter((item) => item.type === 'file')
  const filesByName = new Map(files.map((item) => [item.name.toLocaleLowerCase(), item]))
  const candidates = new Map<string, { base: string; extension: string; versions: FileItem[] }>()

  for (const file of files) {
    const match = file.name.match(AUTOSAVE_PATTERN)
    if (!match) continue
    const base = match[1]
    const extension = match[3].toLocaleLowerCase()
    const key = `${base.toLocaleLowerCase()}.${extension}`
    const candidate = candidates.get(key) || { base, extension, versions: [] }
    candidate.versions.push(file)
    candidates.set(key, candidate)
  }

  const groupedPaths = new Set<string>()
  const fileEntries: BrowserEntry[] = []
  for (const [key, candidate] of candidates) {
    const finalFile = filesByName.get(`${candidate.base}.${candidate.extension}`.toLocaleLowerCase())
    const versions = [...candidate.versions].sort(
      (left, right) => checkpointSequence(right) - checkpointSequence(left),
    )
    if (!finalFile && versions.length < 2) continue

    const primary = finalFile || versions[0]
    const checkpoints = finalFile ? versions : versions.slice(1)
    groupedPaths.add(primary.path)
    for (const version of versions) groupedPaths.add(version.path)
    fileEntries.push({
      kind: 'group',
      key,
      primary,
      checkpoints,
      hasFinal: !!finalFile,
    })
  }

  for (const file of files) {
    if (!groupedPaths.has(file.path)) fileEntries.push({ kind: 'item', item: file })
  }

  fileEntries.sort((left, right) =>
    entryItem(left).name.localeCompare(entryItem(right).name, undefined, {
      numeric: true,
      sensitivity: 'base',
    }),
  )
  return [...directories, ...fileEntries]
})

const visibleEntries = computed(() =>
  browserEntries.value.filter((entry) => {
    const item = entryItem(entry)
    if (activeFilter.value !== 'all' && item.type !== activeFilter.value) return false
    if (!normalizedQuery.value) return true
    return entrySearchText(entry).includes(normalizedQuery.value)
  }),
)

const artifactGroupCount = computed(
  () => browserEntries.value.filter((entry) => entry.kind === 'group').length,
)
const groupedVersionCount = computed(() =>
  browserEntries.value.reduce((total, entry) => {
    if (entry.kind !== 'group') return total
    return total + entry.checkpoints.length + (entry.hasFinal ? 0 : 1)
  }, 0),
)
const resultLabel = computed(() => {
  if (!normalizedQuery.value) return `当前目录显示 ${browserEntries.value.length} 项`
  return `找到 ${visibleEntries.value.length} 项，共 ${browserEntries.value.length} 项`
})
const imagePreviewUrl = computed(() =>
  imagePreviewItem.value ? outputFileUrl(imagePreviewItem.value.path) : '',
)
const metadataEntries = computed(() => {
  const search = metadataQuery.value.trim().toLocaleLowerCase()
  return Object.entries(metadata.value?.metadata || {})
    .filter(([key, value]) => !search || `${key} ${value}`.toLocaleLowerCase().includes(search))
    .sort(([left], [right]) => {
      const leftPriority = metadataPriority.get(left) ?? Number.MAX_SAFE_INTEGER
      const rightPriority = metadataPriority.get(right) ?? Number.MAX_SAFE_INTEGER
      return leftPriority - rightPriority || left.localeCompare(right)
    })
})

function entryItem(entry: BrowserEntry) {
  return entry.kind === 'group' ? entry.primary : entry.item
}

function entrySearchText(entry: BrowserEntry) {
  const entries = entry.kind === 'group' ? [entry.primary, ...entry.checkpoints] : [entry.item]
  return entries
    .map((item) => `${item.name} ${item.type === 'file' ? fileExtension(item.name) : '文件夹'}`)
    .join(' ')
    .toLocaleLowerCase()
}

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
  expandedGroups.value = new Set()
}

async function goUp() {
  if (loading.value || !canGoUp.value) return
  const parent = locations.value[locations.value.length - 2]
  const loaded = await loadDirectory(parent.requestPath)
  if (!loaded) return
  locations.value.pop()
  query.value = ''
  expandedGroups.value = new Set()
}

function refresh() {
  void loadDirectory(currentLocation.value.requestPath)
}

function clearSearch() {
  query.value = ''
}

function toggleGroup(key: string) {
  const next = new Set(expandedGroups.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  expandedGroups.value = next
}

function isGroupExpanded(group: ArtifactGroup) {
  if (expandedGroups.value.has(group.key)) return true
  if (!normalizedQuery.value) return false
  return group.checkpoints.some((item) => itemSearchText(item).includes(normalizedQuery.value))
}

function visibleCheckpoints(group: ArtifactGroup) {
  if (!normalizedQuery.value) return group.checkpoints
  const matched = group.checkpoints.filter((item) =>
    itemSearchText(item).includes(normalizedQuery.value),
  )
  return matched.length ? matched : group.checkpoints
}

function itemSearchText(item: FileItem) {
  return `${item.name} ${fileExtension(item.name)}`.toLocaleLowerCase()
}

function checkpointSequence(item: FileItem) {
  const match = item.name.match(AUTOSAVE_PATTERN)
  return match ? Number(match[2]) : -1
}

function checkpointLabel(item: FileItem) {
  const match = item.name.match(AUTOSAVE_PATTERN)
  return match ? `自动保存 · #${match[2]}` : '自动保存的中途产物'
}

function groupedVersions(group: ArtifactGroup) {
  return group.checkpoints.length + (group.hasFinal ? 0 : 1)
}

function fileExtension(name: string) {
  const separator = name.lastIndexOf('.')
  if (separator <= 0 || separator === name.length - 1) return '无扩展名'
  return name.slice(separator + 1).toLocaleUpperCase()
}

function itemKind(item: FileItem) {
  return item.type === 'dir' ? '文件夹' : fileExtension(item.name)
}

function isSafetensors(item: FileItem) {
  return item.type === 'file' && fileExtension(item.name) === 'SAFETENSORS'
}

function isImage(item: FileItem) {
  return item.type === 'file' && IMAGE_EXTENSIONS.has(fileExtension(item.name).toLocaleLowerCase())
}

function formatSize(value: number) {
  if (!Number.isFinite(value) || value <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const unitIndex = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1)
  const amount = value / 1024 ** unitIndex
  const precision = unitIndex === 0 || amount >= 100 ? 0 : amount >= 10 ? 1 : 2
  return `${amount.toFixed(precision)} ${units[unitIndex]}`
}

function formatModified(value: string) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date)
}

function openImagePreview(item: FileItem) {
  imagePreviewItem.value = item
  imageLoadFailed.value = false
  imagePreviewOpen.value = true
}

async function openMetadata(item: FileItem) {
  const requestVersion = ++metadataLoadVersion
  metadataItem.value = item
  metadata.value = null
  metadataError.value = ''
  metadataQuery.value = ''
  metadataLoading.value = true
  metadataOpen.value = true

  try {
    const response = await apiClient.getSafetensorsMetadata(item.path)
    if (requestVersion === metadataLoadVersion) metadata.value = response
  } catch (reason) {
    if (requestVersion === metadataLoadVersion) {
      metadataError.value = reason instanceof Error ? reason.message : String(reason)
    }
  } finally {
    if (requestVersion === metadataLoadVersion) metadataLoading.value = false
  }
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

async function loadFileManagerCapability() {
  try {
    fileManagerCapability.value = await apiClient.getFileManagerCapability()
  } catch (reason) {
    fileManagerCapability.value = {
      available: false,
      platform: 'unknown',
      reason: reason instanceof Error ? reason.message : String(reason),
    }
  }
}

function isRevealing(path: string) {
  return revealingPaths.value.has(path)
}

async function revealInFileManager(item: FileItem) {
  if (!canRevealInFileManager.value || revealingPaths.value.has(item.path)) return
  const next = new Set(revealingPaths.value)
  next.add(item.path)
  revealingPaths.value = next
  try {
    await apiClient.revealOutputPath(item.path)
    const manager = fileManagerCapability.value?.fileManager || '文件资源管理器'
    ElMessage.success(`已在${manager}中显示`)
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : String(reason))
    void loadFileManagerCapability()
  } finally {
    const remaining = new Set(revealingPaths.value)
    remaining.delete(item.path)
    revealingPaths.value = remaining
  }
}

onMounted(() => {
  void loadDirectory('')
  void loadFileManagerCapability()
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
          placeholder="搜索文件或版本"
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
      <span
        v-if="fileManagerCapability && !canRevealInFileManager"
        class="file-manager-unavailable"
        :title="fileManagerUnavailableReason"
      >
        <el-icon><InfoFilled /></el-icon>
        当前环境无法调用文件资源管理器
      </span>
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
          <span v-if="artifactGroupCount">
            <strong>{{ groupedVersionCount }}</strong> 个中途版本已折叠为 {{ artifactGroupCount }} 组
          </span>
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
          <div class="heading-metadata">
            <span>类型</span>
            <span>大小</span>
            <span>修改时间</span>
          </div>
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
          <div><strong>当前目录还没有输出文件</strong></div>
          <el-button :icon="Refresh" :loading="loading" @click="refresh">刷新目录</el-button>
        </div>

        <div v-else-if="visibleEntries.length === 0" class="state-panel">
          <span class="state-icon" aria-hidden="true"><el-icon><Search /></el-icon></span>
          <div><strong>没有匹配的项目</strong></div>
          <el-button @click="clearSearch">清除搜索</el-button>
        </div>

        <template v-for="entry in visibleEntries" v-else :key="entry.kind === 'group' ? entry.key : entry.item.path">
          <section v-if="entry.kind === 'group'" class="artifact-group" role="listitem">
            <article class="file-row group-row">
              <button
                class="tree-toggle"
                type="button"
                :aria-expanded="isGroupExpanded(entry)"
                :aria-label="`${isGroupExpanded(entry) ? '折叠' : '展开'} ${entry.primary.name} 的自动保存版本`"
                @click="toggleGroup(entry.key)"
              >
                <el-icon><ArrowDownBold v-if="isGroupExpanded(entry)" /><ArrowRightBold v-else /></el-icon>
              </button>

              <div class="item-primary">
                <div class="name-line">
                  <strong>{{ entry.primary.name }}</strong>
                  <span class="status-chip" :class="{ interim: !entry.hasFinal }">
                    {{ entry.hasFinal ? '最终产物' : '最新自动保存' }}
                  </span>
                  <span class="version-count">{{ groupedVersions(entry) }} 个中途版本</span>
                </div>
                <code :title="entry.primary.path">{{ entry.primary.path }}</code>
              </div>

              <div class="item-metadata">
                <span class="item-kind">{{ itemKind(entry.primary) }}</span>
                <span class="item-size">{{ formatSize(entry.primary.size) }}</span>
                <time class="item-modified" :datetime="entry.primary.modifiedAt">
                  {{ formatModified(entry.primary.modifiedAt) }}
                </time>
              </div>

              <div class="item-actions">
                <el-button
                  v-if="isSafetensors(entry.primary)"
                  text
                  size="small"
                  :icon="InfoFilled"
                  @click="openMetadata(entry.primary)"
                >
                  元数据
                </el-button>
                <el-button
                  v-else-if="isImage(entry.primary)"
                  text
                  size="small"
                  :icon="ViewIcon"
                  @click="openImagePreview(entry.primary)"
                >
                  查看
                </el-button>
                <el-button
                  v-if="canRevealInFileManager"
                  circle
                  text
                  :icon="FolderOpened"
                  :loading="isRevealing(entry.primary.path)"
                  :aria-label="`在文件资源管理器中显示 ${entry.primary.name}`"
                  title="在文件资源管理器中显示"
                  @click="revealInFileManager(entry.primary)"
                />
                <el-button
                  circle
                  text
                  :icon="CopyDocument"
                  :aria-label="`复制文件 ${entry.primary.name} 的路径`"
                  title="复制路径"
                  @click="copyPath(entry.primary.path, '文件')"
                />
              </div>
            </article>

            <div v-if="isGroupExpanded(entry)" class="version-list" role="list" aria-label="自动保存版本">
              <article
                v-for="checkpoint in visibleCheckpoints(entry)"
                :key="checkpoint.path"
                class="file-row version-row"
                role="listitem"
              >
                <span class="file-icon version" aria-hidden="true"><el-icon><Document /></el-icon></span>
                <div class="item-primary">
                  <div class="name-line">
                    <strong>{{ checkpoint.name }}</strong>
                    <span class="status-chip interim">{{ checkpointLabel(checkpoint) }}</span>
                  </div>
                  <code :title="checkpoint.path">{{ checkpoint.path }}</code>
                </div>

                <div class="item-metadata">
                  <span class="item-kind">{{ itemKind(checkpoint) }}</span>
                  <span class="item-size">{{ formatSize(checkpoint.size) }}</span>
                  <time class="item-modified" :datetime="checkpoint.modifiedAt">
                    {{ formatModified(checkpoint.modifiedAt) }}
                  </time>
                </div>

                <div class="item-actions">
                  <el-button
                    v-if="isSafetensors(checkpoint)"
                    text
                    size="small"
                    :icon="InfoFilled"
                    @click="openMetadata(checkpoint)"
                  >
                    元数据
                  </el-button>
                  <el-button
                    v-if="canRevealInFileManager"
                    circle
                    text
                    :icon="FolderOpened"
                    :loading="isRevealing(checkpoint.path)"
                    :aria-label="`在文件资源管理器中显示 ${checkpoint.name}`"
                    title="在文件资源管理器中显示"
                    @click="revealInFileManager(checkpoint)"
                  />
                  <el-button
                    circle
                    text
                    :icon="CopyDocument"
                    :aria-label="`复制文件 ${checkpoint.name} 的路径`"
                    title="复制路径"
                    @click="copyPath(checkpoint.path, '文件')"
                  />
                </div>
              </article>
            </div>
          </section>

          <article
            v-else
            class="file-row"
            :class="{ directory: entry.item.type === 'dir' }"
            role="listitem"
          >
            <span class="file-icon" :class="{ folder: entry.item.type === 'dir' }" aria-hidden="true">
              <el-icon>
                <FolderOpened v-if="entry.item.type === 'dir'" />
                <Picture v-else-if="isImage(entry.item)" />
                <Document v-else />
              </el-icon>
            </span>

            <button
              v-if="entry.item.type === 'dir'"
              class="item-primary directory-link"
              type="button"
              :aria-label="`打开文件夹 ${entry.item.name}`"
              @click="enterDirectory(entry.item)"
            >
              <strong>{{ entry.item.name }}</strong>
              <code :title="entry.item.path">{{ entry.item.path }}</code>
            </button>
            <div v-else class="item-primary">
              <strong>{{ entry.item.name }}</strong>
              <code :title="entry.item.path">{{ entry.item.path }}</code>
            </div>

            <div class="item-metadata">
              <span class="item-kind" :class="{ folder: entry.item.type === 'dir' }">
                {{ itemKind(entry.item) }}
              </span>
              <span class="item-size">{{ entry.item.type === 'dir' ? '—' : formatSize(entry.item.size) }}</span>
              <time class="item-modified" :datetime="entry.item.modifiedAt">
                {{ formatModified(entry.item.modifiedAt) }}
              </time>
            </div>

            <div class="item-actions">
              <el-button
                v-if="isSafetensors(entry.item)"
                text
                size="small"
                :icon="InfoFilled"
                @click="openMetadata(entry.item)"
              >
                元数据
              </el-button>
              <el-button
                v-else-if="isImage(entry.item)"
                text
                size="small"
                :icon="ViewIcon"
                @click="openImagePreview(entry.item)"
              >
                查看
              </el-button>
              <el-button
                v-if="canRevealInFileManager"
                circle
                text
                :icon="FolderOpened"
                :loading="isRevealing(entry.item.path)"
                :aria-label="`在文件资源管理器中显示 ${entry.item.name}`"
                title="在文件资源管理器中显示"
                @click="revealInFileManager(entry.item)"
              />
              <el-button
                circle
                text
                :icon="CopyDocument"
                :aria-label="`复制${entry.item.type === 'dir' ? '文件夹' : '文件'} ${entry.item.name} 的路径`"
                title="复制路径"
                @click="copyPath(entry.item.path, entry.item.type === 'dir' ? '文件夹' : '文件')"
              />
            </div>
          </article>
        </template>
      </div>
    </section>

    <el-dialog
      v-model="imagePreviewOpen"
      class="output-image-dialog"
      :title="imagePreviewItem?.name || '图片预览'"
      width="min(920px, calc(100vw - 32px))"
      append-to-body
      destroy-on-close
      align-center
    >
      <div class="image-preview-stage">
        <img
          v-if="imagePreviewItem && !imageLoadFailed"
          :src="imagePreviewUrl"
          :alt="imagePreviewItem.name"
          @error="imageLoadFailed = true"
        />
        <div v-else class="preview-fallback">
          <el-icon><Picture /></el-icon>
          <strong>无法加载这张图片</strong>
          <span>文件可能已被移动、删除或格式不受浏览器支持。</span>
        </div>
      </div>
      <div v-if="imagePreviewItem" class="preview-file-info">
        <code :title="imagePreviewItem.path">{{ imagePreviewItem.path }}</code>
        <span>{{ formatSize(imagePreviewItem.size) }}</span>
        <time :datetime="imagePreviewItem.modifiedAt">{{ formatModified(imagePreviewItem.modifiedAt) }}</time>
        <el-button text :icon="CopyDocument" @click="copyPath(imagePreviewItem.path, '图片')">复制路径</el-button>
      </div>
    </el-dialog>

    <el-drawer
      v-model="metadataOpen"
      class="metadata-drawer"
      direction="rtl"
      size="min(720px, 94vw)"
      append-to-body
      destroy-on-close
    >
      <template #header>
        <div class="metadata-heading">
          <span>Safetensors 元数据</span>
          <strong :title="metadataItem?.name">{{ metadataItem?.name }}</strong>
        </div>
      </template>

      <div v-loading="metadataLoading" class="metadata-content">
        <el-alert
          v-if="metadataError"
          type="error"
          title="无法读取元数据"
          :description="metadataError"
          show-icon
          :closable="false"
        >
          <template #default>
            <el-button v-if="metadataItem" size="small" @click="openMetadata(metadataItem)">重试</el-button>
          </template>
        </el-alert>

        <template v-else-if="metadata">
          <dl class="metadata-summary">
            <div><dt>文件大小</dt><dd>{{ formatSize(metadata.size) }}</dd></div>
            <div><dt>修改时间</dt><dd>{{ formatModified(metadata.modifiedAt) }}</dd></div>
            <div><dt>张量数量</dt><dd>{{ metadata.tensorCount }}</dd></div>
            <div><dt>元数据字段</dt><dd>{{ Object.keys(metadata.metadata).length }}</dd></div>
          </dl>

          <div class="metadata-toolbar">
            <el-input
              v-model="metadataQuery"
              :prefix-icon="Search"
              placeholder="搜索键或值"
              clearable
            />
            <el-button :icon="CopyDocument" @click="copyPath(metadata.path, '文件')">复制路径</el-button>
          </div>

          <div v-if="metadataEntries.length" class="metadata-list">
            <article v-for="[key, value] in metadataEntries" :key="key" class="metadata-entry">
              <code>{{ key }}</code>
              <pre>{{ value || '—' }}</pre>
            </article>
          </div>
          <div v-else class="metadata-empty">
            <InfoFilled />
            <strong>{{ metadataQuery ? '没有匹配的元数据' : '文件没有 __metadata__ 字段' }}</strong>
          </div>
        </template>
      </div>
    </el-drawer>
  </section>
</template>

<style scoped>
.outputs-page {
  width: min(100%, var(--page-max));
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

.page-heading,
.current-location,
.item-primary {
  min-width: 0;
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
  justify-content: space-between;
  gap: 16px;
  margin-top: 34px;
}

.file-manager-unavailable {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--text-muted);
  font-size: 12px;
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
}

.location-bar {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  padding: 10px 0;
  border-bottom: 1px solid var(--border-subtle);
}

.current-location {
  display: grid;
  gap: 2px;
}

.current-location > span {
  color: var(--text-strong);
  font-size: 13px;
  font-weight: 650;
}

.current-location code,
.item-primary code,
.preview-file-info code {
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
  margin: 12px 0 0;
}

.file-list {
  min-height: 360px;
  transition: opacity 120ms ease;
}

.file-list.refreshing {
  opacity: 0.58;
  pointer-events: none;
}

.list-heading,
.file-row {
  display: grid;
  grid-template-columns: 38px minmax(250px, 1fr) minmax(336px, 440px) 156px;
  align-items: center;
  gap: 12px;
}

.list-heading {
  min-height: 46px;
  border-bottom: 1px solid var(--border-subtle);
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 620;
}

.list-heading > span:first-child {
  grid-column: 1 / 3;
}

.list-heading > span:last-child {
  text-align: right;
}

.heading-metadata,
.item-metadata {
  display: grid;
  grid-template-columns: minmax(96px, 1fr) minmax(76px, 0.8fr) minmax(146px, 1.3fr);
  align-items: center;
  gap: 12px;
  text-align: right;
}

.file-row {
  position: relative;
  min-height: 66px;
  padding: 0 6px;
  border-bottom: 1px solid var(--border-subtle);
  border-radius: 8px;
}

.file-row:hover {
  background: var(--surface-hover);
}

.tree-toggle,
.file-icon {
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: var(--text-muted);
  font-size: 17px;
}

.tree-toggle {
  cursor: pointer;
}

.tree-toggle:hover {
  background: var(--brand-soft);
  color: var(--text-strong);
}

.file-icon.folder {
  color: var(--brand-strong);
}

.file-icon.version {
  color: var(--warning);
  font-size: 15px;
}

.item-primary {
  display: grid;
  gap: 4px;
  padding: 10px 0;
}

.item-primary > strong,
.name-line strong {
  overflow: hidden;
  color: var(--text-strong);
  font-size: 14px;
  line-height: 1.3;
  font-weight: 640;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.name-line {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 7px;
}

.name-line strong {
  min-width: 0;
}

.status-chip {
  flex: none;
  padding: 2px 7px;
  border-radius: 999px;
  background: var(--success-soft);
  color: var(--success);
  font-size: 11px;
  line-height: 1.5;
  font-weight: 680;
}

.status-chip.interim {
  background: var(--warning-soft);
  color: var(--warning);
}

.version-count {
  flex: none;
  color: var(--text-muted);
  font-size: 11px;
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

.item-kind,
.item-size,
.item-modified {
  overflow: hidden;
  color: var(--text-secondary);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.item-kind.folder {
  color: var(--brand-strong);
}

.item-size {
  font-family: var(--font-mono);
}

.item-modified {
  color: var(--text-muted);
}

.item-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 2px;
}

.item-actions :deep(.el-button + .el-button) {
  margin-left: 0;
}

.artifact-group {
  border-bottom: 1px solid var(--border-subtle);
}

.artifact-group > .file-row,
.version-list .file-row {
  border-bottom: 0;
}

.group-row {
  background: color-mix(in srgb, var(--success-soft) 28%, transparent);
}

.version-list {
  margin: 0 0 5px 21px;
  padding-left: 19px;
  border-left: 1px solid color-mix(in srgb, var(--warning) 35%, var(--border-subtle));
}

.version-row {
  min-height: 62px;
}

.version-row::before {
  position: absolute;
  top: 50%;
  left: -20px;
  width: 18px;
  border-top: 1px solid color-mix(in srgb, var(--warning) 35%, var(--border-subtle));
  content: '';
}

.skeleton-row {
  min-height: 68px;
  display: grid;
  align-items: center;
  border-bottom: 1px solid var(--border-subtle);
}

.skeleton-row :deep(.el-skeleton__template) {
  display: grid;
  grid-template-columns: 38px minmax(0, 1fr) 160px;
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
  width: 132px;
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

.image-preview-stage {
  min-height: min(68vh, 680px);
  display: grid;
  place-items: center;
  overflow: hidden;
  border-radius: 10px;
  background: var(--surface-sunken);
}

.image-preview-stage img {
  max-width: 100%;
  max-height: min(68vh, 680px);
  display: block;
  object-fit: contain;
}

.preview-fallback {
  display: grid;
  justify-items: center;
  gap: 8px;
  padding: 48px 20px;
  color: var(--text-muted);
  text-align: center;
}

.preview-fallback :deep(.el-icon) {
  font-size: 32px;
}

.preview-fallback strong {
  color: var(--text-strong);
}

.preview-file-info {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto auto;
  align-items: center;
  gap: 12px;
  padding-top: 14px;
  color: var(--text-muted);
  font-size: 12px;
}

.metadata-heading {
  min-width: 0;
  display: grid;
  gap: 3px;
}

.metadata-heading > span {
  color: var(--text-muted);
  font-size: 12px;
}

.metadata-heading > strong {
  overflow: hidden;
  color: var(--text-strong);
  font-size: 16px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.metadata-content {
  min-height: 240px;
}

.metadata-summary {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1px;
  margin: 0 0 20px;
  overflow: hidden;
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  background: var(--border-subtle);
}

.metadata-summary > div {
  padding: 12px 14px;
  background: var(--surface-sunken);
}

.metadata-summary dt {
  color: var(--text-muted);
  font-size: 11px;
}

.metadata-summary dd {
  margin: 4px 0 0;
  color: var(--text-strong);
  font-family: var(--font-mono);
  font-size: 13px;
}

.metadata-toolbar {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  margin-bottom: 14px;
}

.metadata-list {
  display: grid;
  gap: 8px;
}

.metadata-entry {
  padding: 11px 13px;
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  background: var(--surface-sunken);
}

.metadata-entry > code {
  display: block;
  margin-bottom: 7px;
  color: var(--brand-strong);
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 680;
  overflow-wrap: anywhere;
}

.metadata-entry > pre {
  max-height: 240px;
  margin: 0;
  overflow: auto;
  color: var(--text-secondary);
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.55;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.metadata-empty {
  min-height: 220px;
  display: grid;
  place-content: center;
  justify-items: center;
  gap: 10px;
  color: var(--text-muted);
}

.metadata-empty svg {
  width: 28px;
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

@media (max-width: 1080px) {
  .list-heading,
  .file-row {
    grid-template-columns: 36px minmax(220px, 1fr) minmax(300px, 370px) 136px;
  }

  .heading-metadata,
  .item-metadata {
    grid-template-columns: 82px 72px minmax(138px, 1fr);
  }
}

@media (max-width: 820px) {
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

  .browser-toolbar {
    align-items: flex-start;
    flex-direction: column;
    gap: 10px;
  }

  .list-heading {
    display: none;
  }

  .file-row {
    width: 100%;
    max-width: 100%;
    grid-template-columns: 34px minmax(0, 1fr);
    gap: 9px;
    min-height: 92px;
    box-sizing: border-box;
    padding: 9px 132px 9px 0;
  }

  .item-primary {
    padding: 2px 0;
  }

  .item-metadata {
    grid-column: 2;
    grid-row: 2;
    display: flex;
    flex-wrap: wrap;
    justify-content: flex-start;
    gap: 5px 13px;
    text-align: left;
  }

  .item-actions {
    position: absolute;
    top: 50%;
    right: 2px;
    transform: translateY(-50%);
  }

  .name-line {
    flex-wrap: wrap;
  }

  .name-line strong {
    flex-basis: 100%;
  }

  .version-list {
    margin-left: 16px;
    padding-left: 12px;
  }

  .version-row::before {
    left: -13px;
    width: 11px;
  }

  .preview-file-info {
    grid-template-columns: minmax(0, 1fr) auto;
  }
}

@media (max-width: 520px) {
  .location-bar {
    padding: 10px 0;
  }

  .directory-stats {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 6px 12px;
  }

  .directory-stats span:nth-child(n + 3) {
    grid-column: 1 / -1;
  }

  .item-actions :deep(.el-button--small span) {
    display: none;
  }

  .item-actions :deep(.el-button--small) {
    width: 32px;
    padding: 8px;
  }

  .metadata-summary {
    grid-template-columns: minmax(0, 1fr);
  }

  .metadata-toolbar {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (prefers-reduced-motion: reduce) {
  .file-list {
    transition: none;
  }
}
</style>
