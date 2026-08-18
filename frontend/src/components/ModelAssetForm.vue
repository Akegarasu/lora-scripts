<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import { Check } from '@element-plus/icons-vue'

import type { ParamDefinition } from '@/api/types'
import { useDraftStore } from '@/stores/draft'
import ParamControl from './ParamControl.vue'

const props = defineProps<{
  params: ParamDefinition[]
}>()

const draft = useDraftStore()
const touched = reactive(new Set<string>())

function isRequired(param: ParamDefinition) {
  return param.required || param.priority === 'required'
}

// Required model assets first (these differ per family: FLUX wants clip_l/t5xxl/ae,
// Anima wants qwen3/llm_adapter, etc.), then the optional ones.
const ordered = computed(() =>
  [...props.params].sort((a, b) => Number(isRequired(b)) - Number(isRequired(a))),
)

watch(
  () => props.params,
  () => touched.clear(),
)

function hasValue(param: ParamDefinition) {
  const value = draft.getValue(param)
  return value !== undefined && value !== null && value !== ''
}

function isMissing(param: ParamDefinition) {
  return touched.has(param.name) && isRequired(param) && !hasValue(param)
}

function updateValue(param: ParamDefinition, value: unknown) {
  touched.add(param.name)
  draft.setValue(param, value)
}

function assetDescription(param: ParamDefinition) {
  return param.description || param.help || ''
}
</script>

<template>
  <div class="asset-grid">
    <section
      v-for="param in ordered"
      :id="`param-${param.name}`"
      :key="param.name"
      class="asset-card"
      :class="{
        'asset-required': isRequired(param),
        'asset-missing': isMissing(param),
        'asset-ready': hasValue(param),
      }"
      role="group"
      :aria-labelledby="`asset-title-${param.name}`"
    >
      <div class="asset-head">
        <div class="asset-title">
          <strong :id="`asset-title-${param.name}`">
            {{ param.label || param.name }}
            <span v-if="isRequired(param)" class="required-mark" aria-label="必填">*</span>
          </strong>
          <el-tag v-if="param.deprecated" size="small" type="warning" effect="plain">
            已弃用
          </el-tag>
        </div>
        <el-tag v-if="hasValue(param)" class="asset-status" size="small" type="success" effect="light">
          <el-icon aria-hidden="true"><Check /></el-icon>
          已选择
        </el-tag>
        <el-tag
          v-else
          size="small"
          :class="{ 'meta-tag': !isRequired(param) }"
          :type="isRequired(param) ? 'warning' : 'info'"
          effect="plain"
        >
          {{ isRequired(param) ? '需要配置' : '可选' }}
        </el-tag>
      </div>
      <code class="asset-flag">{{ param.name }}</code>
      <p v-if="assetDescription(param)" class="asset-description">{{ assetDescription(param) }}</p>
      <ParamControl
        :param="param"
        :model-value="draft.getValue(param)"
        @update:model-value="updateValue(param, $event)"
      />
      <span v-if="isMissing(param)" class="asset-error" role="alert">请选择或输入有效路径</span>
    </section>
  </div>
</template>

<style scoped>
.asset-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.asset-card {
  display: grid;
  align-content: start;
  gap: 7px;
  min-width: 0;
  padding: 14px;
  border: 0;
  border-radius: 8px;
  background: var(--surface-sunken);
  scroll-margin-top: 20px;
  transition:
    border-color 160ms ease,
    box-shadow 160ms ease;
}

.asset-required {
  border-left: 0;
}

.asset-missing {
  background: var(--danger-soft);
  box-shadow: none;
}

.asset-ready {
  border-color: transparent;
}

.asset-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.asset-title {
  min-width: 0;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}

.asset-title strong {
  min-width: 0;
  font-size: 14px;
  font-weight: 650;
}

.required-mark {
  margin-left: 2px;
  color: var(--el-color-danger);
}

.asset-status {
  flex: none;
}

.asset-status :deep(.el-tag__content) {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.meta-tag {
  --ui-tag-color: var(--text-secondary);
  --ui-tag-background: var(--surface-sunken);
  --ui-tag-border: var(--border);
}

.asset-flag {
  overflow: hidden;
  color: var(--el-text-color-secondary, #687787);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.asset-description {
  margin: 0 0 2px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.55;
}

.asset-error {
  color: var(--el-color-danger);
  font-size: 13px;
  line-height: 1.4;
}

@media (max-width: 720px) {
  .asset-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (prefers-reduced-motion: reduce) {
  .asset-card {
    transition: none;
  }
}
</style>
