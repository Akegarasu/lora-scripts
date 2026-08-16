<script lang="ts">
export type CaptionGalleryStatusType = 'primary' | 'success' | 'warning' | 'info' | 'danger'

export interface CaptionGalleryItem {
  id: string
  name: string
  relativePath: string
  imageUrl: string
  previewUrl?: string
  width?: number
  height?: number
  captionText?: string
  emptyText?: string
  statusLabel?: string
  statusType?: CaptionGalleryStatusType
  error?: string
  selectable?: boolean
}
</script>

<script setup lang="ts">
import { Picture } from '@element-plus/icons-vue'
import { ElImageViewer } from 'element-plus'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RecycleScroller } from 'vue-virtual-scroller'

const props = withDefaults(defineProps<{
  items: CaptionGalleryItem[]
  total: number
  offset: number
  pageSize: number
  loading?: boolean
  selectionEnabled?: boolean
  selectedIds?: string[]
  emptyTitle?: string
  emptyDescription?: string
}>(), {
  loading: false,
  selectionEnabled: false,
  selectedIds: () => [],
  emptyTitle: '没有符合条件的图片',
  emptyDescription: '尝试调整筛选条件或重新扫描数据集。',
})

const emit = defineEmits<{
  'update:selectedIds': [value: string[]]
  'page-change': [page: number]
  'page-size-change': [size: number]
}>()

const root = ref<HTMLElement | null>(null)
const containerWidth = ref(960)
const failedImages = ref(new Set<string>())
const viewerVisible = ref(false)
const viewerIndex = ref(0)
let resizeObserver: ResizeObserver | undefined

const rowHeight = 300
const columnCount = computed(() => {
  const width = containerWidth.value
  if (width < 520) return 1
  return Math.max(1, Math.min(5, Math.floor(width / 220)))
})
const cellWidth = computed(() => Math.max(180, Math.floor(containerWidth.value / columnCount.value)))
const rowCount = computed(() => Math.ceil(props.items.length / columnCount.value))
const scrollerHeight = computed(() => Math.min(720, Math.max(rowHeight, rowCount.value * rowHeight)))
const layoutKey = computed(() => `${props.offset}-${props.pageSize}-${columnCount.value}-${cellWidth.value}`)
const currentPage = computed(() => Math.floor(props.offset / props.pageSize) + 1)
const paginationLayout = computed(() =>
  containerWidth.value >= 680
    ? 'total, sizes, prev, pager, next, jumper'
    : 'prev, pager, next',
)
const selected = computed(() => new Set(props.selectedIds))
const selectableItems = computed(() => props.items.filter((item) => item.selectable !== false))
const pageAllSelected = computed(
  () => selectableItems.value.length > 0 && selectableItems.value.every((item) => selected.value.has(item.id)),
)
const viewableItems = computed(() =>
  props.items.filter((item) => !!item.imageUrl && !failedImages.value.has(item.id)),
)
const viewerUrls = computed(() =>
  viewableItems.value.map((item) => item.previewUrl || item.imageUrl),
)
const activeViewerItem = computed(() => viewableItems.value[viewerIndex.value] || null)

watch(
  () => props.items.map((item) => item.id),
  (ids) => {
    const visibleIds = new Set(ids)
    failedImages.value = new Set([...failedImages.value].filter((id) => visibleIds.has(id)))
    if (viewerVisible.value && viewerIndex.value >= viewableItems.value.length) closeViewer()
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

function toggleItem(item: CaptionGalleryItem, checked: boolean) {
  if (!props.selectionEnabled || item.selectable === false) return
  const next = new Set(props.selectedIds)
  if (checked) next.add(item.id)
  else next.delete(item.id)
  emit('update:selectedIds', [...next])
}

function togglePage() {
  const next = new Set(props.selectedIds)
  for (const item of selectableItems.value) {
    if (pageAllSelected.value) next.delete(item.id)
    else next.add(item.id)
  }
  emit('update:selectedIds', [...next])
}

function markImageFailed(itemId: string) {
  const next = new Set(failedImages.value)
  next.add(itemId)
  failedImages.value = next
}

function openViewer(item: CaptionGalleryItem) {
  const index = viewableItems.value.findIndex((candidate) => candidate.id === item.id)
  if (index < 0) return
  viewerIndex.value = index
  viewerVisible.value = true
}

function closeViewer() {
  viewerVisible.value = false
}
</script>

<template>
  <section ref="root" class="paged-gallery" aria-label="分页图片图库">
    <div v-if="selectionEnabled" class="selection-bar">
      <el-button :disabled="selectableItems.length === 0" @click="togglePage">
        {{ pageAllSelected ? '取消选择本页' : '选择本页可用图片' }}
      </el-button>
      <span>已选 {{ selectedIds.length }} 张；选择会跨分页保留。</span>
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
      >
        <template #default="{ item }">
          <div class="gallery-cell">
            <article
              class="gallery-card"
              :class="{ selected: selected.has(item.id), invalid: !!item.error }"
            >
              <div class="image-wrap">
                <button
                  v-if="!failedImages.has(item.id)"
                  class="image-button"
                  type="button"
                  :aria-label="`预览 ${item.name}`"
                  @click="openViewer(item)"
                >
                  <img
                    :src="item.imageUrl"
                    :alt="item.name"
                    loading="lazy"
                    @error="markImageFailed(item.id)"
                  />
                </button>
                <div v-else class="image-fallback">
                  <el-icon><Picture /></el-icon>
                  <span>无法预览</span>
                </div>
                <el-checkbox
                  v-if="selectionEnabled"
                  class="item-check"
                  :model-value="selected.has(item.id)"
                  :disabled="item.selectable === false"
                  :aria-label="`选择 ${item.name}`"
                  @click.stop
                  @change="(checked: boolean | string | number) => toggleItem(item, Boolean(checked))"
                />
                <span class="resolution">{{ item.width || '?' }} × {{ item.height || '?' }}</span>
              </div>

              <div class="card-body">
                <div class="item-heading">
                  <strong :title="item.relativePath">{{ item.name }}</strong>
                  <el-tag v-if="item.statusLabel" :type="item.statusType || 'info'">
                    {{ item.statusLabel }}
                  </el-tag>
                </div>
                <p v-if="item.error" class="item-error" :title="item.error">{{ item.error }}</p>
                <p v-else-if="item.captionText" class="caption-preview" :title="item.captionText">
                  {{ item.captionText }}
                </p>
                <p v-else class="caption-empty">{{ item.emptyText || '当前没有 Caption' }}</p>
                <button class="preview-link" type="button" @click="openViewer(item)">
                  查看大图
                </button>
              </div>
            </article>
          </div>
        </template>
      </RecycleScroller>

      <div v-else-if="!loading" class="empty-result">
        <el-icon><Picture /></el-icon>
        <strong>{{ emptyTitle }}</strong>
        <span>{{ emptyDescription }}</span>
      </div>
    </div>

    <el-pagination
      v-if="total > 0"
      class="gallery-pagination"
      background
      :layout="paginationLayout"
      :current-page="currentPage"
      :page-size="pageSize"
      :page-sizes="[50, 100, 200]"
      :total="total"
      @current-change="(page: number) => emit('page-change', page)"
      @size-change="(size: number) => emit('page-size-change', size)"
    />

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
      @close="closeViewer"
    />
    <Teleport to="body">
      <div v-if="viewerVisible && activeViewerItem" class="viewer-caption">
        <strong>{{ activeViewerItem.name }}</strong>
        <span>{{ activeViewerItem.captionText || activeViewerItem.emptyText || '当前没有 Caption' }}</span>
      </div>
    </Teleport>
  </section>
</template>

<style scoped>
.paged-gallery {
  min-width: 0;
  display: grid;
  gap: 12px;
}

.selection-bar {
  display: flex;
  align-items: center;
  gap: 12px;
}

.selection-bar span {
  color: var(--text-muted);
  font-size: 13px;
}

.gallery-stage {
  min-height: 180px;
}

.gallery-scroller {
  width: 100%;
  min-height: 300px;
  overflow-y: auto;
  overscroll-behavior: contain;
}

.gallery-cell {
  width: 100%;
  height: 300px;
  padding: 6px;
}

.gallery-card {
  height: 100%;
  min-width: 0;
  overflow: hidden;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  background: var(--surface);
}

.gallery-card.selected {
  border-color: color-mix(in srgb, var(--brand) 55%, var(--border));
  background: var(--brand-softer);
}

.gallery-card.invalid {
  border-color: color-mix(in srgb, var(--danger) 28%, var(--border));
}

.image-wrap {
  position: relative;
  height: 158px;
  overflow: hidden;
  background: var(--surface-sunken);
}

.image-button {
  width: 100%;
  height: 100%;
  display: block;
  padding: 0;
  border: 0;
  background: transparent;
  cursor: zoom-in;
}

.image-button img {
  width: 100%;
  height: 100%;
  display: block;
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
  font-size: 25px;
}

.item-check {
  position: absolute;
  top: 9px;
  left: 9px;
  min-width: 30px;
  min-height: 30px;
  display: grid;
  place-items: center;
  border: 1px solid rgb(255 255 255 / 70%);
  border-radius: 7px;
  background: rgb(20 20 20 / 58%);
}

.item-check :deep(.el-checkbox__label) {
  display: none;
}

.resolution {
  position: absolute;
  right: 7px;
  bottom: 7px;
  padding: 3px 6px;
  border-radius: 5px;
  background: rgb(18 18 18 / 66%);
  color: white;
  font-size: 13px;
  font-weight: 620;
}

.card-body {
  display: grid;
  gap: 7px;
  padding: 10px;
}

.item-heading {
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 7px;
}

.item-heading strong {
  min-width: 0;
  overflow: hidden;
  color: var(--text-strong);
  font-size: 14px;
  font-weight: 650;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.caption-preview,
.caption-empty,
.item-error {
  min-height: 39px;
  margin: 0;
  display: -webkit-box;
  overflow: hidden;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.5;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.caption-empty {
  color: var(--text-muted);
}

.item-error {
  color: var(--danger);
}

.preview-link {
  justify-self: start;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--brand-strong);
  font: inherit;
  font-size: 13px;
  font-weight: 640;
  cursor: zoom-in;
}

.empty-result {
  min-height: 180px;
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

.empty-result span {
  font-size: 13px;
}

.gallery-pagination {
  justify-self: center;
  max-width: 100%;
}

.viewer-caption {
  position: fixed;
  z-index: 2601;
  left: 50%;
  bottom: 22px;
  width: min(720px, calc(100vw - 120px));
  transform: translateX(-50%);
  display: grid;
  gap: 4px;
  padding: 11px 14px;
  border: 1px solid rgb(255 255 255 / 18%);
  border-radius: 10px;
  background: rgb(18 18 18 / 84%);
  color: white;
  backdrop-filter: blur(8px);
  pointer-events: none;
}

.viewer-caption strong,
.viewer-caption span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.viewer-caption strong {
  font-size: 14px;
}

.viewer-caption span {
  color: rgb(255 255 255 / 78%);
  font-size: 13px;
}

@media (max-width: 640px) {
  .selection-bar {
    align-items: flex-start;
    flex-direction: column;
  }

  .gallery-pagination {
    justify-self: stretch;
    display: flex;
    justify-content: center;
  }

  .viewer-caption {
    bottom: 74px;
    width: calc(100vw - 28px);
  }
}
</style>
