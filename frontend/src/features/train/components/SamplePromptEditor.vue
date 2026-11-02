<script setup lang="ts">
import { computed, watch } from 'vue'
import { CopyDocument, Delete, Plus } from '@element-plus/icons-vue'
import { ElMessageBox } from 'element-plus'

import type { SamplePromptDraft } from '@/api/types'
import ParameterHelp from '@/components/ParameterHelp.vue'
import { useCatalogStore } from '@/stores/catalog'
import { useDraftStore } from '@/stores/draft'
import { sampleDefaults } from '@/utils/sampleDefaults'

const draft = useDraftStore()
const catalog = useCatalogStore()

const usesGuidance = computed(() =>
  ['flux', 'chroma', 'lumina', 'hunyuan_image', 'anima'].includes(catalog.selectedTrainer?.family || ''),
)

const sampleSamplerDefinition = computed(() =>
  catalog.allParams.find((param) => param.name === 'sample_sampler'),
)
const samplerChoices = computed(() =>
  (sampleSamplerDefinition.value?.extra?.fixedValue ? [] : sampleSamplerDefinition.value?.choices || [])
    .filter((choice): choice is string => typeof choice === 'string')
    .map((choice) => ({ label: choice, value: choice })),
)
const samplerPlaceholder = computed(() => {
  if (catalog.loading) return '正在加载采样器…'
  if (sampleSamplerDefinition.value?.extra?.fixedValue) {
    return `固定使用 ${sampleSamplerDefinition.value.extra.fixedValue}`
  }
  if (!samplerChoices.value.length) return '当前训练器未提供采样器'
  return '使用训练器默认值'
})

watch(
  samplerChoices,
  (choices) => {
    const selected = draft.sample.sampler
    if (selected && (choices.length || sampleSamplerDefinition.value?.extra?.fixedValue) && !choices.some((choice) => choice.value === selected)) {
      draft.sample.sampler = undefined
    }
  },
  { immediate: true },
)

function newPrompt(): SamplePromptDraft {
  return {
    prompt: '',
    negativePrompt: '',
    width: draft.dataset.resolution[0] || 1024,
    height: draft.dataset.resolution[1] || 1024,
    seed: 1337,
    ...sampleDefaults(catalog.selectedTrainerId),
    ...(usesGuidance.value ? { guidanceScale: 1 } : {}),
  }
}

function addPrompt() {
  draft.sample.prompts.push(newPrompt())
}

function duplicatePrompt(prompt: SamplePromptDraft) {
  draft.sample.prompts.push(JSON.parse(JSON.stringify(prompt)) as SamplePromptDraft)
}

async function removePrompt(index: number) {
  const prompt = draft.sample.prompts[index]
  if (!prompt) return
  if (prompt.prompt.trim() || prompt.negativePrompt?.trim()) {
    try {
      await ElMessageBox.confirm(
        `将从当前草稿中删除第 ${index + 1} 组采样提示词，无法撤销。`,
        '删除采样提示词',
        { confirmButtonText: '删除', cancelButtonText: '保留', type: 'warning', autofocus: false },
      )
    } catch {
      return
    }
  }
  const currentIndex = draft.sample.prompts.indexOf(prompt)
  if (currentIndex !== -1) draft.sample.prompts.splice(currentIndex, 1)
}

function applyDatasetResolution(prompt: SamplePromptDraft) {
  prompt.width = draft.dataset.resolution[0]
  prompt.height = draft.dataset.resolution[1]
}

function updateEpochSchedule(value: number | undefined) {
  draft.sample.everyNEpochs = value
  if (value !== undefined) draft.sample.everyNSteps = undefined
}

function updateStepSchedule(value: number | undefined) {
  draft.sample.everyNSteps = value
  if (value !== undefined) draft.sample.everyNEpochs = undefined
}
</script>

<template>
  <div class="sample-editor">
    <ParameterHelp class="sample-toggle" content="采样会延长训练时间；固定 Seed 便于比较训练前后的效果。" label="采样说明">
      <span class="sample-label">
        <strong>训练中生成预览图</strong>
      </span>
      <el-switch
        v-model="draft.sample.enabled"
        inline-prompt
        aria-label="启用训练中采样"
      />
    </ParameterHelp>

    <template v-if="draft.sample.enabled">
      <div class="sample-schedule">
        <ParameterHelp class="schedule-field" content="Epoch 与 Step 间隔二选一，填写一个会清空另一个。" label="采样间隔说明">
          <span><label for="sample-epochs">每 N 个 Epoch</label></span>
          <el-input-number
            id="sample-epochs"
            aria-label="每 N 个 Epoch 采样"
            :model-value="draft.sample.everyNEpochs"
            :min="1"
            controls-position="right"
            placeholder="不按 Epoch 采样"
            @update:model-value="updateEpochSchedule"
          />
        </ParameterHelp>
        <ParameterHelp as="label" class="schedule-field" for="sample-steps" content="Epoch 与 Step 间隔二选一，填写一个会清空另一个。" label="采样间隔说明">
          <span>每 N 个 Step</span>
          <el-input-number
            id="sample-steps"
            aria-label="每 N 个 Step 采样"
            :model-value="draft.sample.everyNSteps"
            :min="1"
            controls-position="right"
            placeholder="不按 Step 采样"
            @update:model-value="updateStepSchedule"
          />
        </ParameterHelp>
        <label for="sample-sampler">
          <span>采样器</span>
          <el-select
            id="sample-sampler"
            aria-label="采样器"
            v-model="draft.sample.sampler"
            clearable
            filterable
            :disabled="samplerChoices.length === 0"
            :placeholder="samplerPlaceholder"
          >
            <el-option
              v-for="choice in samplerChoices"
              :key="choice.value"
              :label="choice.label"
              :value="choice.value"
            />
          </el-select>
        </label>
      </div>

      <div class="prompt-list">
        <article v-for="(prompt, index) in draft.sample.prompts" :key="index" class="prompt-card">
          <header class="prompt-header">
            <div>
              <span class="prompt-index">{{ String(index + 1).padStart(2, '0') }}</span>
              <strong>采样提示词</strong>
            </div>
            <div class="prompt-actions">
              <el-button
                text
                size="small"
                :icon="CopyDocument"
                :aria-label="`复制第 ${index + 1} 条提示词`"
                @click="duplicatePrompt(prompt)"
              >
                复制
              </el-button>
              <el-button
                text
                size="small"
                type="danger"
                :icon="Delete"
                :aria-label="`删除第 ${index + 1} 条提示词`"
                @click="removePrompt(index)"
              >
                删除
              </el-button>
            </div>
          </header>

          <label class="prompt-field">
            <span>正向提示词 <em aria-label="必填">*</em></span>
            <el-input
              v-model="prompt.prompt"
              :aria-label="`第 ${index + 1} 组正向提示词`"
              aria-required="true"
              type="textarea"
              :autosize="{ minRows: 3, maxRows: 7 }"
              placeholder="描述希望在训练预览中看到的主体、构图与风格"
            />
          </label>

          <label class="prompt-field">
            <span>负向提示词</span>
            <el-input
              v-model="prompt.negativePrompt"
              :aria-label="`第 ${index + 1} 组负向提示词`"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 4 }"
              placeholder="不希望出现的内容"
            />
          </label>

          <div class="prompt-options">
            <label>
              <span>宽度</span>
              <el-input-number v-model="prompt.width" :aria-label="`第 ${index + 1} 组宽度`" :min="64" :step="64" controls-position="right" />
            </label>
            <label>
              <span>高度</span>
              <el-input-number v-model="prompt.height" :aria-label="`第 ${index + 1} 组高度`" :min="64" :step="64" controls-position="right" />
            </label>
            <label>
              <span>Steps</span>
              <el-input-number v-model="prompt.steps" :aria-label="`第 ${index + 1} 组 Steps`" :min="1" controls-position="right" />
            </label>
            <label>
              <span>Seed</span>
              <el-input-number v-model="prompt.seed" :aria-label="`第 ${index + 1} 组 Seed`" controls-position="right" />
            </label>
            <label>
              <span>CFG</span>
              <el-input-number v-model="prompt.cfgScale" :aria-label="`第 ${index + 1} 组 CFG`" :min="0" :step="0.5" controls-position="right" />
            </label>
            <label v-if="usesGuidance">
              <span>Guidance</span>
              <el-input-number v-model="prompt.guidanceScale" :aria-label="`第 ${index + 1} 组 Guidance`" :min="0" :step="0.5" controls-position="right" />
            </label>
          </div>

          <button class="resolution-link" type="button" @click="applyDatasetResolution(prompt)">
            使用数据集分辨率 {{ draft.dataset.resolution[0] }} × {{ draft.dataset.resolution[1] }}
          </button>
        </article>

        <button class="add-prompt" type="button" @click="addPrompt">
          <span><el-icon><Plus /></el-icon></span>
          <strong>添加采样提示词</strong>
        </button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.sample-editor {
  display: grid;
  gap: 20px;
}

.sample-toggle {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  justify-content: space-between;
  gap: 6px 20px;
  padding: 4px 0;
}

.sample-toggle strong {
  color: var(--text-strong);
  font-size: 14px;
  font-weight: 650;
}

.sample-label,
.sample-schedule label > span,
.schedule-field > span {
  display: flex;
  align-items: center;
  gap: 6px;
}

.sample-schedule {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 180px), 1fr));
  align-items: start;
  gap: 14px;
}

.sample-schedule > label,
.schedule-field,
.prompt-field,
.prompt-options label {
  min-width: 0;
  display: grid;
  gap: 7px;
}

.sample-schedule label > span,
.schedule-field > span,
.prompt-field > span,
.prompt-options label > span {
  color: var(--text-strong);
  font-size: 13px;
  font-weight: 620;
}

.sample-schedule :deep(.el-input-number),
.prompt-options :deep(.el-input-number) {
  width: 100%;
}

.sample-schedule p {
  grid-column: 1 / -1;
  margin: -4px 0 0;
  color: var(--text-muted);
  font-size: 12px;
}

.prompt-list {
  display: grid;
  gap: 14px;
}

.prompt-card {
  display: grid;
  gap: 14px;
  padding: 16px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  background: var(--surface-raised);
}

.prompt-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
}

.prompt-header > div {
  display: flex;
  align-items: center;
  gap: 9px;
}

.prompt-index {
  color: var(--brand-strong);
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 700;
}

.prompt-header strong {
  color: var(--text-strong);
  font-size: 14px;
  font-weight: 650;
}

.prompt-actions {
  display: flex;
  align-items: center;
}

.prompt-field em {
  margin-left: 5px;
  color: var(--warning);
  font-size: 12px;
  font-style: normal;
  font-weight: 560;
}

.prompt-field small {
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 500;
}

.prompt-options {
  display: grid;
  grid-template-columns: repeat(3, minmax(100px, 1fr));
  gap: 12px;
}

.resolution-link {
  justify-self: start;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--brand-strong);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}

.resolution-link:hover {
  text-decoration: underline;
}

.add-prompt {
  width: 100%;
  min-height: 56px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border: 0;
  border-radius: var(--radius-lg);
  background: var(--surface-sunken);
  color: var(--text-secondary);
  text-align: left;
  cursor: pointer;
}

.add-prompt:hover {
  background: var(--surface-hover);
  color: var(--brand-strong);
}

.add-prompt > span {
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  border-radius: 10px;
  background: var(--brand-soft);
}

.add-prompt strong {
  color: var(--text-strong);
  font-size: 14px;
  font-weight: 630;
}

@media (max-width: 640px) {
  .sample-schedule {
    grid-template-columns: 1fr;
  }

  .sample-schedule p {
    grid-column: auto;
  }

  .prompt-options {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .prompt-header {
    align-items: flex-start;
  }

  .prompt-actions :deep(.el-button span) {
    display: none;
  }
}
</style>
