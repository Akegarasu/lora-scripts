<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Search } from '@element-plus/icons-vue'

import { apiAssetUrl } from '@/api/client'
import { useCaptionStore } from '@/stores/caption'

import CaptionPagedGallery, { type CaptionGalleryItem } from './CaptionPagedGallery.vue'

const props = defineProps<{
  selectedIds: string[]
  selectionEnabled: boolean
}>()

const emit = defineEmits<{
  'update:selectedIds': [value: string[]]
  'update:selectionEnabled': [value: boolean]
}>()

const caption = useCaptionStore()
const query = ref('')
const captionState = ref('all')
let searchTimer: number | undefined

const galleryItems = computed<CaptionGalleryItem[]>(() =>
  caption.datasetItems.map((item) => ({
    id: item.id,
    name: item.name,
    relativePath: item.relativePath,
    imageUrl: sizedAssetUrl(item.thumbnailUrl, 384),
    previewUrl: sizedAssetUrl(item.thumbnailUrl, 2048),
    width: item.width,
    height: item.height,
    captionText: item.captionText,
    emptyText: '当前没有 Caption',
    statusLabel: item.error ? '不可处理' : item.captionExists ? '已有' : '待生成',
    statusType: item.error ? 'danger' : item.captionExists ? 'success' : 'info',
    error: item.error,
    selectable: item.writable,
  })),
)

watch(query, () => {
  if (query.value === caption.datasetQuery) return
  if (searchTimer !== undefined) window.clearTimeout(searchTimer)
  searchTimer = window.setTimeout(() => {
    void caption.loadDatasetItems({ offset: 0, query: query.value })
  }, 280)
})

watch(captionState, (state) => {
  if (state === caption.datasetCaptionState) return
  void caption.loadDatasetItems({ offset: 0, captionState: state })
})

watch(
  () => caption.dataset?.id,
  () => {
    query.value = caption.datasetQuery
    captionState.value = caption.datasetCaptionState
  },
)

onBeforeUnmount(() => {
  if (searchTimer !== undefined) window.clearTimeout(searchTimer)
})

function sizedAssetUrl(path: string, size: number) {
  const separator = path.includes('?') ? '&' : '?'
  return apiAssetUrl(`${path}${separator}size=${size}`)
}

function updateSelectionEnabled(enabled: boolean | string | number) {
  const next = Boolean(enabled)
  emit('update:selectionEnabled', next)
  if (!next && props.selectedIds.length) emit('update:selectedIds', [])
}

function changePage(page: number) {
  void caption.loadDatasetItems({ offset: (page - 1) * caption.datasetLimit })
}

function changePageSize(size: number) {
  void caption.setDatasetPageSize(size)
}
</script>

<template>
  <section v-if="caption.dataset" class="dataset-panel" aria-labelledby="dataset-preview-title">
    <div class="dataset-summary">
      <div>
        <h3 id="dataset-preview-title">
          {{ caption.dataset.path === '.' ? '数据集根目录' : caption.dataset.path }}
        </h3>
      </div>
      <div class="summary-values" aria-label="Caption 覆盖统计">
        <span><strong>{{ caption.dataset.total }}</strong> 张图片</span>
        <span class="success"><strong>{{ caption.dataset.withCaption }}</strong> 已有 Caption</span>
        <span><strong>{{ caption.dataset.withoutCaption }}</strong> 待生成</span>
      </div>
    </div>

    <el-alert
      v-if="caption.dataset.truncated"
      type="warning"
      title="图片数量超过扫描上限"
      description="当前任务只会处理已进入扫描快照的图片；可提高扫描上限或按目录拆分任务。"
      :closable="false"
      show-icon
    />

    <el-alert
      v-if="caption.datasetError"
      type="error"
      :title="caption.datasetError"
      :closable="false"
      show-icon
    />

    <div class="dataset-toolbar">
      <el-input
        v-model="query"
        class="dataset-search"
        :prefix-icon="Search"
        clearable
        placeholder="搜索文件名或 Caption"
        aria-label="搜索扫描结果"
      />
      <el-select v-model="captionState" aria-label="筛选 Caption 状态">
        <el-option label="全部图片" value="all" />
        <el-option label="已有 Caption" value="with" />
        <el-option label="尚无 Caption" value="without" />
        <el-option label="存在错误" value="error" />
      </el-select>
      <label class="selection-toggle">
        <span>
          <strong>手动选择图片</strong>
          <small>默认处理整个扫描结果；只在抽样或局部重跑时开启。</small>
        </span>
        <el-switch
          :model-value="selectionEnabled"
          @change="updateSelectionEnabled"
        />
      </label>
      <span class="result-count">
        当前筛选 {{ caption.datasetItemsTotal }} 项
        <template v-if="selectionEnabled"> · 已选 {{ selectedIds.length }} 项</template>
      </span>
    </div>

    <CaptionPagedGallery
      :items="galleryItems"
      :total="caption.datasetItemsTotal"
      :offset="caption.datasetOffset"
      :page-size="caption.datasetLimit"
      :loading="caption.datasetLoading"
      :selection-enabled="selectionEnabled"
      :selected-ids="selectedIds"
      @update:selected-ids="(ids) => emit('update:selectedIds', ids)"
      @page-change="changePage"
      @page-size-change="changePageSize"
    />

  </section>
</template>

<style scoped>
.dataset-panel {
  min-width: 0;
  display: grid;
  gap: 16px;
  padding-top: 18px;
  border-top: 1px solid var(--border-subtle);
}

.dataset-summary {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
}

.section-kicker {
  color: var(--text-muted);
  font-size: 13px;
  font-weight: 650;
}

.dataset-summary h3 {
  margin: 3px 0 0;
  color: var(--text-strong);
  font-size: 17px;
  font-weight: 680;
}

.summary-values {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 7px;
}

.summary-values span {
  padding: 5px 8px;
  border: 0;
  border-radius: 7px;
  background: var(--surface-sunken);
  color: var(--text-secondary);
  font-size: 13px;
}

.summary-values .success {
  color: var(--success);
  background: var(--success-soft);
}

.dataset-toolbar {
  display: grid;
  grid-template-columns: minmax(230px, 1fr) 170px minmax(250px, auto);
  align-items: center;
  gap: 10px;
}

.selection-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 9px 11px;
  border: 0;
  border-radius: var(--radius-md);
  background: var(--surface-sunken);
}

.selection-toggle > span {
  min-width: 0;
  display: grid;
  gap: 2px;
}

.selection-toggle strong {
  color: var(--text-strong);
  font-size: 14px;
}

.selection-toggle small {
  color: var(--text-muted);
  font-size: 13px;
  line-height: 1.4;
}

.result-count {
  grid-column: 1 / -1;
  color: var(--text-muted);
  font-size: 13px;
}

@media (max-width: 1180px) {
  .dataset-toolbar {
    grid-template-columns: minmax(0, 1fr) 170px;
  }

  .selection-toggle {
    grid-column: 1 / -1;
  }
}

@media (max-width: 760px) {
  .dataset-summary {
    display: grid;
  }

  .summary-values {
    justify-content: flex-start;
  }

  .dataset-toolbar {
    grid-template-columns: 1fr;
  }

  .selection-toggle,
  .result-count {
    grid-column: auto;
  }

  .tag-editor-note {
    display: grid;
  }
}
</style>
