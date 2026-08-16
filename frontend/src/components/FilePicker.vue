<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { ArrowUpBold, Document, FolderOpened, RefreshRight } from '@element-plus/icons-vue'

import { apiClient } from '@/api/client'
import type { FileItem } from '@/api/types'

const props = defineProps<{
  modelValue: boolean
  kind: string
  root: string
  allowDirectories?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  select: [path: string]
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (next) => emit('update:modelValue', next),
})

const currentPath = ref('')
const pathInput = ref('')
const rootPath = ref('')
const items = ref<FileItem[]>([])
const selectedItem = ref<FileItem | null>(null)
const loading = ref(false)
const error = ref('')
const pathInputElement = ref<{ focus: () => void } | null>(null)

const isFolderMode = computed(() => props.kind === 'folder')
const canSelectDirectory = computed(() => isFolderMode.value || !!props.allowDirectories)
const rootLabel = computed(() => {
  const labels: Record<string, string> = {
    models: '模型目录',
    'sd-models': '模型目录',
    train: '数据集目录',
    datasets: '数据集目录',
    output: '输出目录',
    outputs: '输出目录',
    logs: '日志目录',
    workspace: '工作区',
  }
  return labels[props.root] || props.root
})
const rootFallbackPath = computed(() => {
  const paths: Record<string, string> = {
    models: 'sd-models',
    'sd-models': 'sd-models',
    train: 'train',
    datasets: 'train',
    output: 'output',
    outputs: 'output',
    logs: 'logs',
    workspace: '.',
  }
  return paths[props.root] || props.root
})
const currentPathLabel = computed(() => currentPath.value || `${rootLabel.value}（根目录）`)
const currentFolderPath = computed(() => currentPath.value || rootFallbackPath.value)
const canGoUp = computed(() => {
  if (!currentPath.value) return false
  const current = normalizePath(currentPath.value)
  const boundary = normalizePath(rootPath.value)
  if (boundary && current === boundary) return false
  const parent = parentPath(currentPath.value)
  return Boolean(parent) && normalizePath(parent) !== current
})
const canConfirmSelection = computed(() => {
  if (!selectedItem.value) return false
  if (selectedItem.value.type === 'dir') return canSelectDirectory.value
  return !isFolderMode.value
})
const selectionHint = computed(() => {
  if (selectedItem.value) {
    const action = selectedItem.value.type === 'dir' ? '双击进入文件夹' : '双击直接选择文件'
    return `已选中：${selectedItem.value.name} · ${action}`
  }
  return canSelectDirectory.value
    ? '单击选中，双击文件夹可进入；也可直接选择当前文件夹'
    : '单击选中文件，双击直接选择；双击文件夹可进入'
})

watch(
  () => props.modelValue,
  async (next) => {
    if (!next) return
    pathInput.value = currentPath.value
    await load(currentPath.value)
  },
)

watch(
  () => [props.kind, props.root],
  () => {
    currentPath.value = ''
    pathInput.value = ''
    rootPath.value = ''
    items.value = []
    selectedItem.value = null
  },
)

async function load(nextPath = currentPath.value) {
  const requestedPath = nextPath.trim()

  loading.value = true
  error.value = ''
  selectedItem.value = null
  try {
    const data = await apiClient.browseFiles({ kind: props.kind, root: props.root, path: requestedPath })
    items.value = data.items
    currentPath.value = requestedPath || inferDirectory(data.items)
    if (!requestedPath && !rootPath.value) {
      rootPath.value = currentPath.value || rootFallbackPath.value
    }
    pathInput.value = currentPath.value
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
  }
}

function inferDirectory(entries: FileItem[]) {
  return entries.length > 0 ? parentPath(entries[0].path) : ''
}

function normalizePath(value: string) {
  return value.trim().replace(/\\/g, '/').replace(/\/+$/, '').toLowerCase()
}

function parentPath(value: string) {
  const normalized = value.replace(/\\/g, '/').replace(/\/+$/, '')
  const separator = normalized.lastIndexOf('/')
  if (separator < 0) return ''
  if (separator === 0) return '/'
  if (separator === 2 && normalized[1] === ':') return `${normalized.slice(0, 2)}/`
  return normalized.slice(0, separator)
}

async function enterDirectory(item: FileItem) {
  if (item.type !== 'dir') return
  await load(item.path)
}

function selectItem(item: FileItem) {
  selectedItem.value = item
}

function activateItem(item: FileItem) {
  if (item.type === 'dir') {
    void enterDirectory(item)
    return
  }
  choose(item.path)
}

function confirmSelection() {
  if (!selectedItem.value || !canConfirmSelection.value) return
  choose(selectedItem.value.path)
}

function choose(path: string) {
  if (!path) return
  emit('select', path)
  selectedItem.value = null
  visible.value = false
}

function chooseCurrentFolder() {
  if (!canSelectDirectory.value) return
  choose(currentFolderPath.value)
}

async function goUp() {
  if (!canGoUp.value) return
  await load(parentPath(currentPath.value))
}

function openTypedPath() {
  void load(pathInput.value)
}

function formatSize(value: number) {
  if (!value) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const unitIndex = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1)
  const amount = value / 1024 ** unitIndex
  return `${amount.toFixed(unitIndex === 0 || amount >= 10 ? 0 : 1)} ${units[unitIndex]}`
}

function itemTypeLabel(item: FileItem) {
  return item.type === 'dir' ? '文件夹' : '文件'
}

function closeDialog() {
  selectedItem.value = null
  error.value = ''
}

async function focusPathInput() {
  await nextTick()
  pathInputElement.value?.focus()
}
</script>

<template>
  <el-dialog
    v-model="visible"
    class="file-picker-dialog"
    title="选择路径"
    width="min(840px, calc(100vw - 24px))"
    destroy-on-close
    @opened="focusPathInput"
    @closed="closeDialog"
  >
    <div class="current-location" aria-live="polite">
      <el-icon aria-hidden="true"><FolderOpened /></el-icon>
      <span>当前位置</span>
      <strong :title="currentPathLabel">{{ currentPathLabel }}</strong>
    </div>

    <div class="file-picker-toolbar">
      <el-button
        :icon="ArrowUpBold"
        :disabled="!canGoUp || loading"
        aria-label="返回上级目录"
        @click="goUp"
      >
        上级
      </el-button>
      <el-input
        ref="pathInputElement"
        v-model="pathInput"
        clearable
        aria-label="输入要打开的路径"
        :placeholder="`输入路径，当前根目录为${rootLabel}`"
        @keyup.enter="openTypedPath"
      />
      <el-button :icon="RefreshRight" :loading="loading" aria-label="刷新当前目录" @click="load(currentPath)">
        刷新
      </el-button>
      <el-button type="primary" :disabled="loading" @click="openTypedPath">打开路径</el-button>
    </div>

    <p class="picker-instruction">{{ selectionHint }}</p>
    <el-alert v-if="error" type="error" :title="error" show-icon :closable="false" />

    <el-table
      v-loading="loading"
      :data="items"
      height="min(52vh, 460px)"
      highlight-current-row
      row-key="path"
      aria-label="目录内容"
      @row-click="selectItem"
      @row-dblclick="activateItem"
    >
      <el-table-column label="" width="44">
        <template #default="{ row }">
          <el-icon class="file-icon" aria-hidden="true">
            <FolderOpened v-if="row.type === 'dir'" />
            <Document v-else />
          </el-icon>
        </template>
      </el-table-column>
      <el-table-column prop="name" label="名称" min-width="180" show-overflow-tooltip />
      <el-table-column class-name="type-column" label-class-name="type-column" label="类型" width="90">
        <template #default="{ row }">{{ itemTypeLabel(row) }}</template>
      </el-table-column>
      <el-table-column
        class-name="size-column"
        label-class-name="size-column"
        label="大小"
        width="110"
        align="right"
      >
        <template #default="{ row }">{{ row.type === 'dir' ? '—' : formatSize(row.size) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="132" align="right">
        <template #default="{ row }">
          <template v-if="row.type === 'dir'">
            <el-button
              v-if="canSelectDirectory"
              size="small"
              text
              :aria-label="`选择文件夹 ${row.name}`"
              @click.stop="choose(row.path)"
            >
              选择
            </el-button>
            <el-button
              size="small"
              text
              :aria-label="`进入文件夹 ${row.name}`"
              @click.stop="enterDirectory(row)"
            >
              进入
            </el-button>
          </template>
          <el-button v-else size="small" text @click.stop="choose(row.path)">选择</el-button>
        </template>
      </el-table-column>
      <template #empty>
        <div class="picker-empty">
          <el-icon aria-hidden="true"><FolderOpened /></el-icon>
          <strong>当前目录为空</strong>
          <span>{{ kind === 'folder' ? '这里没有子文件夹' : '这里没有符合当前类型的文件' }}</span>
        </div>
      </template>
    </el-table>

    <template #footer>
      <div class="picker-footer">
        <span class="footer-selection" aria-live="polite">
          {{ selectedItem ? `已选中 ${selectedItem.name}` : '尚未选择项目' }}
        </span>
        <div class="footer-actions">
          <el-button @click="visible = false">取消</el-button>
          <el-button v-if="canSelectDirectory" @click="chooseCurrentFolder">
            选择当前文件夹
          </el-button>
          <el-button type="primary" :disabled="!canConfirmSelection" @click="confirmSelection">
            {{ selectedItem?.type === 'dir' ? '选择所选文件夹' : '选择文件' }}
          </el-button>
        </div>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
.current-location {
  display: grid;
  grid-template-columns: auto auto minmax(0, 1fr);
  align-items: center;
  gap: 7px;
  margin-bottom: 10px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.current-location strong {
  overflow: hidden;
  color: var(--el-text-color-primary);
  font-family: "JetBrains Mono", "SFMono-Regular", Consolas, monospace;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-picker-toolbar {
  display: grid;
  grid-template-columns: auto minmax(180px, 1fr) auto auto;
  gap: 8px;
}

.picker-instruction {
  margin: 10px 2px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.file-icon {
  color: var(--el-color-primary);
  font-size: 17px;
}

.picker-empty {
  display: grid;
  justify-items: center;
  gap: 5px;
  padding: 42px 16px;
  color: var(--el-text-color-secondary);
}

.picker-empty .el-icon {
  margin-bottom: 3px;
  color: var(--el-text-color-placeholder);
  font-size: 28px;
}

.picker-empty strong {
  color: var(--el-text-color-primary);
  font-size: 13px;
}

.picker-empty span {
  font-size: 12px;
}

.picker-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.footer-selection {
  min-width: 0;
  overflow: hidden;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.footer-actions {
  display: flex;
  flex: none;
  gap: 8px;
}

@media (max-width: 680px) {
  .file-picker-toolbar {
    grid-template-columns: auto minmax(0, 1fr) auto;
  }

  .file-picker-toolbar > :last-child {
    grid-column: 1 / -1;
  }

  .picker-footer {
    align-items: stretch;
    flex-direction: column;
  }

  .footer-actions {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .footer-actions > :last-child {
    grid-column: 1 / -1;
  }

  :deep(.type-column),
  :deep(.size-column) {
    display: none;
  }
}

@media (max-width: 680px), (max-height: 640px) {
  :global(.file-picker-dialog) {
    width: min(840px, calc(100vw - 16px)) !important;
    height: calc(100dvh - 16px);
    max-height: calc(100dvh - 16px);
    display: flex;
    flex-direction: column;
    margin: 8px auto !important;
  }

  :global(.file-picker-dialog .el-dialog__header) {
    flex: 0 0 auto;
  }

  :global(.file-picker-dialog .el-dialog__body) {
    flex: 1 1 auto;
    min-height: 0;
    overflow: auto;
  }

  :global(.file-picker-dialog .el-dialog__footer) {
    flex: 0 0 auto;
    padding-bottom: calc(12px + env(safe-area-inset-bottom));
    border-top: 1px solid var(--border-subtle);
    background: var(--surface);
  }
}
</style>
