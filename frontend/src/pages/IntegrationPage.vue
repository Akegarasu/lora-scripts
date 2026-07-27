<script setup lang="ts">
defineProps<{ title: string; src: string }>()
</script>

<template>
  <div class="integration-page"><header><div><span class="eyebrow">INTEGRATED SERVICE</span><h1>{{ title }}</h1></div><a :href="src" target="_blank" rel="noreferrer">在新窗口打开</a></header><iframe :title="title" :src="src" /></div>
</template>
