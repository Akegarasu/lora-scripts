<script setup lang="ts">
import { Check, Picture, ZoomIn } from '@element-plus/icons-vue'
import { ElImageViewer } from 'element-plus'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RecycleScroller } from 'vue-virtual-scroller'

import { apiAssetUrl } from '@/api/client'
import type { TagEditorItem } from '@/api/types'

const props = defineProps<{
  items: TagEditorItem[]
  total: number
  offset: number
  pageSize: number
  loading: boolean
  activeId: string
  selectedIds: string[]
  allFiltered: boolean
  excludedIds: string[]
  pendingIds: string[]
}>()

const emit = defineEmits<{
  activate: [item: TagEditorItem]
  toggle: [item: TagEditorItem, checked: boolean]
  'toggle-page': []
  'select-filtered': []
  'clear-selection': []
  'page-change': [page: number]
  'page-size-change': [size: number]
}>()

const root = ref<HTMLElement | null>(null)
const containerWidth = ref(960)
const failedImages = ref(new Set<string>())
const viewerVisible = ref(false)
const viewerIndex = ref(0)
let resizeObserver: ResizeObserver | undefined

const columnCount = computed(() => {
  if (containerWidth.value < 520) return 1
  return Math.max(2, Math.min(6, Math.floor(containerWidth.value / 150)))
})
const rowHeight = computed(() => (columnCount.value === 1 ? 320 : 260))
const cellWidth = computed(() => Math.max(150, Math.floor(containerWidth.value / columnCount.value)))
const rowCount = computed(() => Math.ceil(props.items.length / columnCount.value))
const scrollerHeight = computed(() => {
  const maximum = containerWidth.value < 680 ? 560 : 680
  return Math.min(maximum, Math.max(rowHeight.value, rowCount.value * rowHeight.value))
})
const layoutKey = computed(
  () => `${props.offset}-${props.pageSize}-${columnCount.value}-${cellWidth.value}`,
)
const currentPage = computed(() => Math.floor(props.offset / props.pageSize) + 1)
const pageCount = computed(() => Math.max(1, Math.ceil(props.total / props.pageSize)))
const compactPagination = computed(() => containerWidth.value < 680)
const selected = computed(() => new Set(props.selectedIds))
const excluded = computed(() => new Set(props.excludedIds))
const pending = computed(() => new Set(props.pendingIds))
const writableItems = computed(() => props.items.filter((item) => item.writable && !item.error))
const pageAllSelected = computed(
  () =>
    writableItems.value.length > 0 &&
    writableItems.value.every((item) => isSelected(item.id)),
)
const selectionCount = computed(() =>
  props.allFiltered ? Math.max(0, props.total - props.excludedIds.length) : props.selectedIds.length,
)
const viewableItems = computed(() =>
  props.items.filter((item) => !!item.thumbnailUrl && !failedImages.value.has(item.id)),
)
const viewerUrls = computed(() =>
  viewableItems.value.map((item) => sizedAssetUrl(item.thumbnailUrl, 2048)),
)
const activeViewerItem = computed(() => viewableItems.value[viewerIndex.value] || null)

watch(
  () => props.items.map((item) => item.id),
  (ids) => {
    const visible = new Set(ids)
    failedImages.value = new Set([...failedImages.value].filter((id) => visible.has(id)))
    if (viewerVisible.value && viewerIndex.value >= viewableItems.value.length) {
      viewerVisible.value = false
    }
  },
)

onMounted(async () => {
  await nextTick()
  if (!root.value) return
  const updateWidth = () => {
    if (root.value) containerWidth.value = Math.max(1, root.value.clientWidth)
  }
  updateWidth()
  if (typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(updateWidth)
    resizeObserver.observe(root.value)
  }
})

onBeforeUnmount(() => resizeObserver?.disconnect())

function sizedAssetUrl(path: string, size: number) {
  const separator = path.includes('?') ? '&' : '?'
  return apiAssetUrl(`${path}${separator}size=${size}`)
}

function isSelected(id: string) {
  return props.allFiltered ? !excluded.value.has(id) : selected.value.has(id)
}

function itemStatus(item: TagEditorItem) {
  if (item.error) return { label: '错误', type: 'danger' as const }
  if (!item.captionExists) return { label: '缺失', type: 'info' as const }
  if (!item.captionText.trim()) return { label: '空白', type: 'warning' as const }
  return { label: '已有', type: 'success' as const }
}

function markImageFailed(itemId: string) {
  const next = new Set(failedImages.value)
  next.add(itemId)
  failedImages.value = next
}

function activate(item: TagEditorItem) {
  emit('activate', item)
}

function openViewer(item: TagEditorItem) {
  const index = viewableItems.value.findIndex((candidate) => candidate.id === item.id)
  if (index < 0) return
  viewerIndex.value = index
  viewerVisible.value = true
}
</script>

<template>
  <section ref="root" class="tag-gallery" aria-label="Caption 数据集图库">
    <div class="selection-bar" aria-live="polite">
      <div class="selection-actions">
        <el-button :disabled="writableItems.length === 0" @click="emit('toggle-page')">
          {{ pageAllSelected ? '取消选择本页' : '选择本页' }}
        </el-button>
        <el-button
          v-if="!allFiltered && selectedIds.length > 0 && total > selectedIds.length"
          text
          type="primary"
          @click="emit('select-filtered')"
        >
          选择当前筛选全部 {{ total }} 项
        </el-button>
        <el-button v-if="selectionCount > 0" text @click="emit('clear-selection')">清除选择</el-button>
      </div>
      <span v-if="allFiltered">
        已选择当前筛选 {{ selectionCount }} 项
        <template v-if="excludedIds.length">，排除 {{ excludedIds.length }} 项</template>
      </span>
      <span v-else>已选择 {{ selectedIds.length }} 项</span>
    </div>

    <div v-loading="loading" class="gallery-stage" aria-live="polite">
      <RecycleScroller
        v-if="items.length"
        :key="layoutKey"
        class="gallery-scroller"
        :style="{ height: `${scrollerHeight}px` }"
        :items="items"
        :item-size="rowHeight"
        :grid-items="columnCount"
        :item-secondary-size="cellWidth"
        :buffer="rowHeight"
        key-field="id"
        role="list"
        aria-label="图片与 Caption"
      >
        <template #default="{ item }">
          <div class="gallery-cell">
            <article
              class="gallery-card"
              :class="{
                active: activeId === item.id,
                selected: isSelected(item.id),
                pending: pending.has(item.id),
                invalid: !!item.error,
              }"
              role="listitem"
              tabindex="0"
              :aria-current="activeId === item.id ? 'true' : undefined"
              aria-keyshortcuts="Enter Space"
              :aria-label="`${item.name}，${itemStatus(item).label}`"
              @click="activate(item)"
              @keydown.enter.prevent="activate(item)"
              @keydown.space.prevent="activate(item)"
            >
              <div class="image-wrap">
                <img
                  v-if="!failedImages.has(item.id)"
                  :src="sizedAssetUrl(item.thumbnailUrl, 360)"
                  :alt="item.name"
                  loading="lazy"
                  @error="markImageFailed(item.id)"
                  @dblclick.stop="openViewer(item)"
                />
                <div v-else class="image-fallback">
                  <el-icon><Picture /></el-icon>
                  <span>无法预览</span>
                </div>

                <button
                  type="button"
                  class="select-button"
                  :class="{ selected: isSelected(item.id) }"
                  :disabled="!item.writable || !!item.error"
                  :aria-pressed="isSelected(item.id)"
                  :aria-label="`选择 ${item.name}`"
                  @click.stop="emit('toggle', item, !isSelected(item.id))"
                >
                  <el-icon v-if="isSelected(item.id)"><Check /></el-icon>
                  <span v-else class="selection-ring" aria-hidden="true" />
                </button>
                <button
                  class="zoom-button"
                  type="button"
                  :aria-label="`查看 ${item.name} 大图`"
                  @click.stop="openViewer(item)"
                >
                  <el-icon><ZoomIn /></el-icon>
                </button>
                <span class="resolution">{{ item.width || '?' }} x {{ item.height || '?' }}</span>
              </div>

              <div class="card-body">
                <div class="item-heading">
                  <strong :title="item.relativePath">{{ item.name }}</strong>
                  <div class="item-badges">
                    <el-tag v-if="pending.has(item.id)" type="warning">待应用</el-tag>
                    <el-tag :type="itemStatus(item).type">{{ itemStatus(item).label }}</el-tag>
                  </div>
                </div>
                <p v-if="item.error" class="item-error" :title="item.error">{{ item.error }}</p>
                <p v-else-if="item.captionText" class="caption-preview" :title="item.captionText">
                  {{ item.captionText }}
                </p>
                <p v-else class="caption-empty">
                  {{ item.captionExists ? 'Caption 文件为空' : '没有 Caption 文件' }}
                </p>
                <div class="card-meta">
                  <span v-if="item.tags.length">{{ item.tags.length }} 个标签</span>
                  <span v-if="item.duplicateCount > 1" class="duplicate">
                    重复 {{ item.duplicateCount }} 项
                  </span>
                  <span v-if="item.captionPreviewTruncated">摘要已截断</span>
                </div>
              </div>
            </article>
          </div>
        </template>
      </RecycleScroller>

      <div v-else-if="!loading" class="empty-result">
        <el-icon><Picture /></el-icon>
        <strong>没有符合条件的图片</strong>
        <span>调整搜索或筛选条件后重试。</span>
      </div>
    </div>

    <div v-if="total > 0" class="pagination-row">
      <span v-if="compactPagination" class="mobile-page-summary">
        第 {{ currentPage }} / {{ pageCount }} 页，共 {{ total }} 项
      </span>
      <el-pagination
        class="gallery-pagination"
        background
        :layout="compactPagination ? 'prev, pager, next' : 'total, sizes, prev, pager, next, jumper'"
        :pager-count="compactPagination ? 3 : 7"
        :current-page="currentPage"
        :page-size="pageSize"
        :page-sizes="[50, 100, 200]"
        :total="total"
        @current-change="(page: number) => emit('page-change', page)"
        @size-change="(size: number) => emit('page-size-change', size)"
      />
    </div>

    <ElImageViewer
      v-if="viewerVisible && viewerUrls.length"
      :url-list="viewerUrls"
      :initial-index="viewerIndex"
      :infinite="false"
      :z-index="2600"
      teleported
      show-progress
      hide-on-click-modal
      @switch="(index: number) => (viewerIndex = index)"
      @close="viewerVisible = false"
    />
    <Teleport to="body">
      <div v-if="viewerVisible && activeViewerItem" class="viewer-caption">
        <strong>{{ activeViewerItem.name }}</strong>
        <span>{{ activeViewerItem.captionText || '当前没有 Caption' }}</span>
      </div>
    </Teleport>
  </section>
</template>

<style scoped>
.tag-gallery {
  min-width: 0;
  display: grid;
  gap: 12px;
}

.selection-bar,
.selection-actions,
.pagination-row {
  display: flex;
  align-items: center;
  gap: 8px 12px;
}

.selection-bar {
  min-height: 40px;
  justify-content: space-between;
}

.selection-bar > span,
.mobile-page-summary {
  color: var(--text-muted);
  font-size: 13px;
}

.gallery-stage {
  min-height: 180px;
}

.gallery-scroller {
  width: 100%;
  min-height: 260px;
  overflow-y: auto;
  overscroll-behavior: contain;
}

.gallery-cell {
  width: 100%;
  height: 100%;
  padding: 6px;
}

.gallery-card {
  height: 100%;
  min-width: 0;
  overflow: hidden;
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  background: var(--surface);
  cursor: pointer;
  transition: border-color 140ms ease, background-color 140ms ease;
}

.gallery-card:hover,
.gallery-card.active {
  border-color: var(--brand);
}

.gallery-card.active {
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--brand) 14%, transparent);
}

.gallery-card.selected {
  background: var(--brand-softer);
}

.gallery-card.pending {
  border-color: color-mix(in srgb, var(--warning) 46%, var(--border));
}

.gallery-card.invalid {
  border-color: color-mix(in srgb, var(--danger) 42%, var(--border));
}

.image-wrap {
  position: relative;
  height: 126px;
  overflow: hidden;
  background: var(--surface-sunken);
}

.image-wrap > img {
  width: 100%;
  height: 100%;
  display: block;
  object-fit: contain;
}

.image-fallback {
  height: 100%;
  display: grid;
  place-items: center;
  align-content: center;
  gap: 6px;
  color: var(--text-muted);
  font-size: 13px;
}

.image-fallback .el-icon {
  font-size: 25px;
}

.select-button,
.zoom-button {
  position: absolute;
  top: 8px;
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  padding: 0;
  border: 1px solid rgb(255 255 255 / 46%);
  border-radius: 50%;
  background: rgb(24 24 27 / 68%);
  color: white;
  box-shadow: 0 2px 8px rgb(0 0 0 / 16%);
  backdrop-filter: blur(6px);
  transition: transform 140ms ease, background-color 140ms ease, opacity 140ms ease;
}

.select-button {
  left: 8px;
  cursor: pointer;
}

.select-button:hover:not(:disabled),
.zoom-button:hover {
  transform: translateY(-1px);
  background: rgb(24 24 27 / 86%);
}

.select-button.selected {
  border-color: color-mix(in srgb, var(--brand) 78%, white);
  background: var(--brand);
}

.select-button:disabled {
  opacity: 0.42;
  cursor: not-allowed;
}

.selection-ring {
  width: 14px;
  height: 14px;
  border: 2px solid currentColor;
  border-radius: 50%;
}

.zoom-button {
  right: 8px;
  cursor: zoom-in;
}

.resolution {
  position: absolute;
  right: 7px;
  bottom: 7px;
  padding: 3px 6px;
  border-radius: 5px;
  background: rgb(18 18 18 / 68%);
  color: white;
  font-size: 12px;
  font-weight: 620;
}

.card-body {
  display: grid;
  gap: 6px;
  padding: 8px;
}

.item-heading {
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 7px;
}

.item-heading > strong {
  min-width: 0;
  overflow: hidden;
  color: var(--text-strong);
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.item-badges,
.card-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 5px 8px;
}

.item-badges {
  flex: none;
}

.caption-preview,
.caption-empty,
.item-error {
  min-height: 39px;
  margin: 0;
  display: -webkit-box;
  overflow: hidden;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.5;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.caption-empty {
  color: var(--text-muted);
}

.item-error,
.duplicate {
  color: var(--danger);
}

.card-meta {
  color: var(--text-muted);
  font-size: 11px;
}

.empty-result {
  min-height: 220px;
  display: grid;
  place-items: center;
  align-content: center;
  gap: 7px;
  color: var(--text-muted);
  text-align: center;
}

.empty-result .el-icon {
  font-size: 30px;
}

.empty-result strong {
  color: var(--text-strong);
  font-size: 15px;
}

.pagination-row {
  justify-content: center;
  flex-wrap: wrap;
}

.gallery-pagination {
  max-width: 100%;
}

.viewer-caption {
  position: fixed;
  z-index: 2601;
  left: 50%;
  bottom: 22px;
  width: min(760px, calc(100vw - 120px));
  transform: translateX(-50%);
  display: grid;
  gap: 4px;
  padding: 11px 14px;
  border: 1px solid rgb(255 255 255 / 18%);
  border-radius: 8px;
  background: rgb(18 18 18 / 86%);
  color: white;
  pointer-events: none;
}

.viewer-caption strong,
.viewer-caption span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.viewer-caption span {
  color: rgb(255 255 255 / 78%);
  font-size: 13px;
}

@media (max-width: 680px) {
  .selection-bar {
    align-items: flex-start;
    flex-direction: column;
  }

  .selection-actions {
    width: 100%;
    flex-wrap: wrap;
  }

  .gallery-scroller {
    min-height: 320px;
  }

  .image-wrap {
    height: 180px;
  }

  .pagination-row {
    display: grid;
    justify-items: center;
  }

  .viewer-caption {
    bottom: calc(74px + env(safe-area-inset-bottom));
    width: calc(100vw - 28px);
  }
}
</style>
