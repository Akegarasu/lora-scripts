<script setup lang="ts">
import { computed } from "vue"
const props = defineProps<{ title: string; src: string; configurable?: boolean }>()
const resolvedSrc = computed(() => {
  if (!props.configurable) return props.src
  try {
    const settings = JSON.parse(localStorage.getItem("ui-configs") || "{}") as { tensorboard_url?: string }
    return settings.tensorboard_url?.trim() || props.src
  } catch { return props.src }
})
</script>

<template>
  <div class="integration-page"><header><div><span class="eyebrow">INTEGRATED SERVICE</span><h1>{{ title }}</h1></div><a :href="resolvedSrc" target="_blank" rel="noreferrer">在新窗口打开</a></header><iframe :title="title" :src="resolvedSrc" /></div>
</template>
