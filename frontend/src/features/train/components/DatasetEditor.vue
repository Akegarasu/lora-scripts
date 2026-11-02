<script setup lang="ts">
import { computed, ref } from 'vue'
import { WarningFilled } from '@element-plus/icons-vue'

import FilePicker from '@/components/FilePicker.vue'
import ParameterHelp from '@/components/ParameterHelp.vue'
import { useCatalogStore } from '@/stores/catalog'
import { useDraftStore } from '@/stores/draft'

const catalog = useCatalogStore()
const draft = useDraftStore()
const pickerVisible = ref(false)

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
    <div class="config-block">
      <div class="form-grid">
        <ParameterHelp class="field field-wide" content="包含训练图片与同名 Caption 文件的目录。启动时会检查目录中是否有可用图片。" label="图片目录说明">
          <span class="field-label">
            <label for="dataset-path">图片目录 <em>必填</em></label>
          </span>
          <el-input
            id="dataset-path"
            aria-label="图片目录"
            v-model="draft.dataset.root"
            clearable
            aria-required="true"
            placeholder="例如 C:/datasets/my_character"
          >
            <template #append>
              <el-button aria-label="选择训练图片目录" @click="pickerVisible = true">选择目录</el-button>
            </template>
          </el-input>
        </ParameterHelp>

        <ParameterHelp class="field" content="与图片同名的描述文件后缀。" label="Caption 后缀说明">
          <span class="field-label">
            <label for="caption-extension">Caption 后缀</label>
          </span>
          <el-select
            id="caption-extension"
            aria-label="Caption 后缀"
            v-model="draft.dataset.captionExtension"
            allow-create
            default-first-option
            filterable
            placeholder=".txt"
          >
            <el-option label=".txt（常用）" value=".txt" />
            <el-option label=".caption" value=".caption" />
          </el-select>
        </ParameterHelp>

        <ParameterHelp class="field" content="建议与目标模型的原生分辨率一致。" label="训练分辨率建议">
          <span class="field-label">
            训练分辨率
          </span>
          <div class="number-pair" aria-label="训练分辨率">
            <el-input-number
              v-model="draft.dataset.resolution[0]"
              aria-label="训练分辨率宽度"
              :min="64"
              :step="bucketAlignment"
              controls-position="right"
            />
            <span aria-hidden="true">×</span>
            <el-input-number
              v-model="draft.dataset.resolution[1]"
              aria-label="训练分辨率高度"
              :min="64"
              :step="bucketAlignment"
              controls-position="right"
            />
          </div>
        </ParameterHelp>

        <ParameterHelp class="field" content="每批训练的图片数量；显存不足时保持为 1。" label="Batch Size 说明">
          <span class="field-label">
            <label for="dataset-batch">Batch Size</label>
          </span>
          <el-input-number
            id="dataset-batch"
            aria-label="Batch Size"
            v-model="draft.dataset.batchSize"
            :min="1"
            controls-position="right"
          />
        </ParameterHelp>

        <ParameterHelp class="field" content="每个 Epoch 重复读取该数据集的次数。" label="重复次数说明">
          <span class="field-label">
            <label for="dataset-repeats">重复次数</label>
          </span>
          <el-input-number
            id="dataset-repeats"
            aria-label="重复次数"
            v-model="draft.dataset.numRepeats"
            :min="1"
            controls-position="right"
          />
        </ParameterHelp>
      </div>
    </div>

    <div class="config-block">
      <div class="block-heading compact">
        <div>
          <h3>分桶与 Caption</h3>
        </div>
        <label class="switch-label">
          <span>启用分桶</span>
          <el-switch v-model="draft.dataset.enableBucket" aria-label="启用分桶" />
        </label>
      </div>

      <div class="form-grid">
        <ParameterHelp
          class="field field-wide"
          :class="{ disabled: !draft.dataset.enableBucket }"
          :content="`基础粒度为 ${bucketAlignment}；根据图片宽高比匹配分桶。范围边界必须能被步长整除。`"
          label="分桶范围说明"
        >
          <span class="field-label">
            分桶范围
          </span>
          <div class="bucket-grid">
            <label>
              <span>最小边长</span>
              <el-input-number
                v-model="draft.dataset.minBucketReso"
                aria-label="分桶最小边长"
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
                aria-label="分桶最大边长"
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
                aria-label="分桶步长"
                :disabled="!draft.dataset.enableBucket"
                :min="1"
                :step="bucketAlignment"
                controls-position="right"
              />
            </label>
          </div>
          <small v-if="!bucketRangeValid" class="field-error" role="alert">
            <el-icon><WarningFilled /></el-icon>
            最大边长需不小于最小边长；步长需为 {{ bucketAlignment }} 的倍数，范围边界也必须能被步长整除。
          </small>
        </ParameterHelp>

        <label class="option-card" :class="{ disabled: !draft.dataset.enableBucket }">
          <span>
            <strong>禁止放大图片</strong>
          </span>
          <el-switch v-model="draft.dataset.bucketNoUpscale" aria-label="禁止放大图片" :disabled="!draft.dataset.enableBucket" />
        </label>

        <ParameterHelp class="option-card" content="适合逗号分隔标签；与文本编码器缓存可能冲突。" label="随机打乱 Caption 说明">
          <span>
            <label for="dataset-shuffle-caption"><strong>随机打乱 Caption</strong></label>
          </span>
          <el-switch id="dataset-shuffle-caption" v-model="draft.dataset.shuffleCaption" aria-label="随机打乱 Caption" />
        </ParameterHelp>

        <ParameterHelp class="field" content="打乱 Caption 时保留开头若干标签。" label="固定前置 Token 说明">
          <span class="field-label">
            <label for="keep-tokens">固定前置 Token</label>
          </span>
          <el-input-number
            id="keep-tokens"
            aria-label="固定前置 Token"
            v-model="draft.dataset.keepTokens"
            :min="0"
            controls-position="right"
          />
        </ParameterHelp>
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
  align-items: start;
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
  display: flex;
  align-items: center;
  gap: 6px;
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
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  justify-content: space-between;
  gap: 6px 18px;
  min-height: 54px;
  padding: 12px 14px;
  border: 0;
  border-radius: var(--radius-md);
  background: var(--surface-sunken);
}

.option-card > span {
  display: flex;
  align-items: center;
  gap: 6px;
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
