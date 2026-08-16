<script setup lang="ts">
import { computed, ref } from 'vue'
import { FolderOpened, Picture, WarningFilled } from '@element-plus/icons-vue'

import FilePicker from '@/components/FilePicker.vue'
import { useCatalogStore } from '@/stores/catalog'
import { useDraftStore } from '@/stores/draft'

const catalog = useCatalogStore()
const draft = useDraftStore()
const pickerVisible = ref(false)

const resolutionLabel = computed(() => `${draft.dataset.resolution[0]} × ${draft.dataset.resolution[1]}`)
const bucketAlignment = computed(() => {
  const value = Number(catalog.selectedTrainer?.datasetDefaults.bucketResoSteps)
  return Number.isFinite(value) && value > 0 ? value : 64
})
const bucketRangeValid = computed(
  () =>
    !draft.dataset.enableBucket ||
    (draft.dataset.minBucketReso > 0 &&
      draft.dataset.maxBucketReso >= draft.dataset.minBucketReso &&
      draft.dataset.bucketResoSteps > 0 &&
      draft.dataset.bucketResoSteps % bucketAlignment.value === 0 &&
      draft.dataset.minBucketReso % draft.dataset.bucketResoSteps === 0 &&
      draft.dataset.maxBucketReso % draft.dataset.bucketResoSteps === 0),
)
</script>

<template>
  <div class="dataset-editor">
    <div class="dataset-source" :class="{ empty: !draft.dataset.root }">
      <span class="source-icon" aria-hidden="true">
        <el-icon><Picture /></el-icon>
      </span>
      <div class="source-copy">
        <strong>{{ draft.dataset.root ? '训练图像目录' : '还没有选择数据集' }}</strong>
        <span v-if="draft.dataset.root" :title="draft.dataset.root">{{ draft.dataset.root }}</span>
        <span v-else>选择包含图片与同名 Caption 的文件夹</span>
      </div>
      <el-button :icon="FolderOpened" @click="pickerVisible = true">
        {{ draft.dataset.root ? '更换目录' : '选择目录' }}
      </el-button>
    </div>

    <div class="config-block">
      <div class="block-heading">
        <div>
          <h3>基础设置</h3>
        </div>
        <span class="summary-chip">{{ resolutionLabel }} · Batch {{ draft.dataset.batchSize }}</span>
      </div>

      <div class="form-grid">
        <label class="field field-wide" for="dataset-path">
          <span class="field-label">图片目录 <em>必填</em></span>
          <el-input
            id="dataset-path"
            v-model="draft.dataset.root"
            clearable
            placeholder="例如 C:/datasets/my_character"
          >
            <template #append>
              <el-button aria-label="浏览数据集目录" @click="pickerVisible = true">浏览</el-button>
            </template>
          </el-input>
          <small>目录中至少需要一张受支持的图片；正式启动时会由后端检查。</small>
        </label>

        <label class="field" for="caption-extension">
          <span class="field-label">Caption 后缀</span>
          <el-select
            id="caption-extension"
            v-model="draft.dataset.captionExtension"
            allow-create
            default-first-option
            filterable
            placeholder=".txt"
          >
            <el-option label=".txt（常用）" value=".txt" />
            <el-option label=".caption" value=".caption" />
          </el-select>
          <small>与图片同名的描述文件后缀。</small>
        </label>

        <div class="field">
          <span class="field-label">训练分辨率</span>
          <div class="number-pair" aria-label="训练分辨率">
            <el-input-number
              v-model="draft.dataset.resolution[0]"
              aria-label="宽度"
              :min="64"
              :step="bucketAlignment"
              controls-position="right"
            />
            <span aria-hidden="true">×</span>
            <el-input-number
              v-model="draft.dataset.resolution[1]"
              aria-label="高度"
              :min="64"
              :step="bucketAlignment"
              controls-position="right"
            />
          </div>
          <small>建议与目标模型的原生分辨率一致。</small>
        </div>

        <label class="field" for="dataset-batch">
          <span class="field-label">Batch Size</span>
          <el-input-number
            id="dataset-batch"
            v-model="draft.dataset.batchSize"
            :min="1"
            controls-position="right"
          />
          <small>显存不足时保持为 1。</small>
        </label>

        <label class="field" for="dataset-repeats">
          <span class="field-label">重复次数</span>
          <el-input-number
            id="dataset-repeats"
            v-model="draft.dataset.numRepeats"
            :min="1"
            controls-position="right"
          />
          <small>每个 epoch 重复读取该数据集的次数。</small>
        </label>
      </div>
    </div>

    <div class="config-block">
      <div class="block-heading compact">
        <div>
          <h3>分桶与 Caption</h3>
        </div>
        <label class="switch-label">
          <span>启用分桶</span>
          <el-switch v-model="draft.dataset.enableBucket" />
        </label>
      </div>

      <div class="form-grid">
        <div class="field field-wide" :class="{ disabled: !draft.dataset.enableBucket }">
          <span class="field-label">Bucket 范围</span>
          <div class="bucket-grid">
            <label>
              <span>最小边长</span>
              <el-input-number
                v-model="draft.dataset.minBucketReso"
                :disabled="!draft.dataset.enableBucket"
                :min="64"
                :step="bucketAlignment"
                controls-position="right"
              />
            </label>
            <label>
              <span>最大边长</span>
              <el-input-number
                v-model="draft.dataset.maxBucketReso"
                :disabled="!draft.dataset.enableBucket"
                :min="64"
                :step="bucketAlignment"
                controls-position="right"
              />
            </label>
            <label>
              <span>步长</span>
              <el-input-number
                v-model="draft.dataset.bucketResoSteps"
                :disabled="!draft.dataset.enableBucket"
                :min="1"
                :step="bucketAlignment"
                controls-position="right"
              />
            </label>
          </div>
          <small v-if="bucketRangeValid">
            当前训练器以 {{ bucketAlignment }} 为基础粒度，系统会自动匹配最接近的宽高比。
          </small>
          <small v-else class="field-error">
            <el-icon><WarningFilled /></el-icon>
            最大边长需不小于最小边长；步长需为 {{ bucketAlignment }} 的倍数，范围边界也必须能被步长整除。
          </small>
        </div>

        <label class="option-card" :class="{ disabled: !draft.dataset.enableBucket }">
          <span>
            <strong>禁止放大图片</strong>
            <small>只缩小超出范围的图片，避免低清素材被强行放大。</small>
          </span>
          <el-switch v-model="draft.dataset.bucketNoUpscale" :disabled="!draft.dataset.enableBucket" />
        </label>

        <label class="option-card">
          <span>
            <strong>随机打乱 Caption</strong>
            <small>适合逗号分隔标签；与文本编码器缓存可能冲突。</small>
          </span>
          <el-switch v-model="draft.dataset.shuffleCaption" />
        </label>

        <label class="field" for="keep-tokens">
          <span class="field-label">固定前置 Token</span>
          <el-input-number
            id="keep-tokens"
            v-model="draft.dataset.keepTokens"
            :min="0"
            controls-position="right"
          />
          <small>打乱 Caption 时保留开头若干标签。</small>
        </label>
      </div>
    </div>

    <FilePicker
      v-model="pickerVisible"
      kind="folder"
      root="train"
      @select="(path) => (draft.dataset.root = path)"
    />
  </div>
</template>

<style scoped>
.dataset-editor {
  display: grid;
  gap: 24px;
}

.dataset-source {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 13px;
  padding: 14px;
  border: 0;
  border-radius: var(--radius-md);
  background: var(--brand-softer);
}

.dataset-source.empty {
  background: var(--surface-sunken);
}

.source-icon {
  width: 38px;
  height: 38px;
  display: grid;
  place-items: center;
  border-radius: 11px;
  background: var(--brand-soft);
  color: var(--brand-strong);
  font-size: 18px;
}

.source-copy {
  min-width: 0;
  display: grid;
  gap: 3px;
}

.source-copy strong {
  color: var(--text-strong);
  font-size: 14px;
  font-weight: 650;
}

.source-copy span {
  overflow: hidden;
  color: var(--text-secondary);
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.config-block {
  display: grid;
  gap: 16px;
}

.config-block + .config-block {
  padding-top: 22px;
  border-top: 1px solid var(--border-subtle);
}

.block-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
}

.block-heading h3 {
  margin: 0;
  color: var(--text-strong);
  font-size: 15px;
  font-weight: 670;
}

.block-heading p {
  margin: 4px 0 0;
  color: var(--text-muted);
  font-size: 13px;
}

.summary-chip {
  flex: 0 0 auto;
  min-height: 26px;
  display: inline-flex;
  align-items: center;
  padding: 3px 8px;
  border: 0;
  border-radius: 6px;
  background: var(--surface-sunken);
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 620;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px 20px;
}

.field {
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 7px;
}

.field-wide {
  grid-column: 1 / -1;
}

.field-label {
  color: var(--text-strong);
  font-size: 13px;
  font-weight: 620;
}

.field-label em {
  margin-left: 4px;
  color: var(--danger);
  font-size: 12px;
  font-style: normal;
  font-weight: 600;
}

.field small,
.option-card small {
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.45;
}

.field :deep(.el-input-number) {
  width: 100%;
}

.number-pair {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  align-items: center;
  gap: 8px;
  color: var(--text-muted);
}

.switch-label {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 600;
}

.bucket-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.bucket-grid label {
  min-width: 0;
  display: grid;
  gap: 6px;
}

.bucket-grid label > span {
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 600;
}

.option-card {
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  min-height: 72px;
  padding: 12px 14px;
  border: 0;
  border-radius: var(--radius-md);
  background: var(--surface-sunken);
}

.option-card > span {
  display: grid;
  gap: 4px;
}

.option-card strong {
  color: var(--text-strong);
  font-size: 13px;
  font-weight: 630;
}

.field-error {
  display: flex;
  align-items: center;
  gap: 5px;
  color: var(--danger) !important;
}

@media (max-width: 680px) {
  .dataset-source {
    grid-template-columns: auto minmax(0, 1fr);
  }

  .dataset-source > .el-button {
    grid-column: 1 / -1;
  }

  .form-grid {
    grid-template-columns: 1fr;
  }

  .field-wide {
    grid-column: auto;
  }

  .bucket-grid {
    grid-template-columns: 1fr;
  }

  .block-heading {
    align-items: flex-start;
    flex-direction: column;
    gap: 10px;
  }

  .block-heading.compact {
    flex-direction: row;
  }
}
</style>
