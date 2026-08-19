<script setup lang="ts">
import { computed } from 'vue'

import type { JobState } from '@/api/types'

const props = defineProps<{ state?: JobState }>()

type TagType = 'primary' | 'success' | 'warning' | 'danger' | 'info'

const META: Record<JobState, { label: string; type: TagType }> = {
  created: { label: '已创建', type: 'info' },
  queued: { label: '排队中', type: 'info' },
  running: { label: '运行中', type: 'primary' },
  succeeded: { label: '成功', type: 'success' },
  failed: { label: '失败', type: 'danger' },
  terminating: { label: '终止中', type: 'warning' },
  terminated: { label: '已终止', type: 'info' },
  canceled: { label: '已取消', type: 'info' },
}

const meta = computed(() => (props.state ? META[props.state] : undefined))
</script>

<template>
  <el-tag
    v-if="meta"
    class="state-badge"
    :class="`is-${state}`"
    :type="meta.type"
    :aria-label="`任务状态：${meta.label}`"
    :title="`任务状态：${meta.label}`"
    size="small"
    effect="light"
  >
    <span class="state-dot" aria-hidden="true" />
    {{ meta.label }}
  </el-tag>
  <el-tag
    v-else
    class="state-badge is-unknown"
    type="info"
    aria-label="任务状态未知"
    size="small"
    effect="light"
  >
    <span class="state-dot" aria-hidden="true" />
    未知
  </el-tag>
</template>

<style scoped>
.state-badge {
  font-weight: 600;
  letter-spacing: 0;
}

.state-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  margin-right: 5px;
  border-radius: 50%;
  background: currentColor;
  vertical-align: 1px;
}

.is-running .state-dot {
  animation: state-pulse 1.8s ease-in-out infinite;
}

.state-badge.is-terminated,
.state-badge.is-canceled,
.state-badge.is-unknown {
  --ui-tag-color: var(--text-secondary);
  --ui-tag-background: var(--surface-sunken);
  --ui-tag-border: var(--border);
}

@keyframes state-pulse {
  0%,
  100% {
    opacity: 1;
    transform: scale(1);
  }

  50% {
    opacity: 0.45;
    transform: scale(0.8);
  }
}

@media (prefers-reduced-motion: reduce) {
  .is-running .state-dot {
    animation: none;
  }
}
</style>
