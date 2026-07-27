<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import { useRoute } from "vue-router"
import { Menu as MenuIcon, Moon, Sunny } from "@element-plus/icons-vue"
import { storeToRefs } from "pinia"
import { useAppStore } from "../stores/app"

const route = useRoute()
const mobileOpen = ref(false)
const dark = ref(document.documentElement.classList.contains("dark"))
const appStore = useAppStore()
const { version } = storeToRefs(appStore)
const groups = [
  { title: "训练", items: [["LoRA 训练", "/lora/index.html"], ["新手模式", "/lora/basic.html"], ["专家模式", "/lora/master.html"], ["Flux LoRA", "/lora/flux.html"], ["Anima LoRA", "/lora/sd3.html"], ["Anima Fast", "/lora/anima-fast.html"], ["全量微调", "/lora/anima-finetune.html"]] },
  { title: "工具与调试", items: [["数据集打标", "/tagger.html"], ["标签编辑", "/native-tageditor.html"], ["TensorBoard", "/tensorboard.html"], ["训练任务", "/task.html"], ["LoRA 脚本工具", "/lora/tools.html"]] },
  { title: "帮助", items: [["新手上路", "/help/guide.html"], ["训练 UI 设置", "/other/settings.html"], ["更新日志", "/other/changelog.html"], ["关于", "/other/about.html"]] },
] as const
const currentPath = computed(() => route.path)
onMounted(() => appStore.loadVersion())

function toggleTheme() {
  dark.value = !dark.value
  document.documentElement.classList.toggle("dark", dark.value)
  localStorage.setItem("vuepress-color-scheme", dark.value ? "dark" : "light")
}
</script>

<template>
  <div class="app-shell">
    <header class="mobile-header">
      <button class="icon-button" aria-label="打开导航" @click="mobileOpen = !mobileOpen"><el-icon><MenuIcon /></el-icon></button>
      <RouterLink class="mobile-brand" to="/">Next Trainer</RouterLink>
      <button class="icon-button" aria-label="切换主题" @click="toggleTheme"><el-icon><Moon v-if="!dark" /><Sunny v-else /></el-icon></button>
    </header>
    <button v-if="mobileOpen" class="sidebar-mask" aria-label="关闭导航" @click="mobileOpen = false" />
    <aside class="sidebar" :class="{ 'is-open': mobileOpen }">
      <RouterLink class="brand" to="/" @click="mobileOpen = false">
        <span class="brand-mark">N</span><span><strong>Next Trainer</strong><small>{{ version ? `v${version}` : "Vue 3 workspace" }}</small></span>
      </RouterLink>
      <nav class="navigation" aria-label="主导航">
        <section v-for="group in groups" :key="group.title" class="nav-group">
          <h2>{{ group.title }}</h2>
          <RouterLink v-for="([label, path], index) in group.items" :key="path" :to="path" class="nav-link" :class="{ active: currentPath === path, nested: index > 0 && group.title === '训练' }" @click="mobileOpen = false">{{ label }}</RouterLink>
        </section>
      </nav>
      <footer class="sidebar-footer">
        <a href="https://github.com/wochenlong/lora-scripts-next" target="_blank" rel="noreferrer">GitHub</a>
        <button class="icon-button" aria-label="切换主题" @click="toggleTheme"><el-icon><Moon v-if="!dark" /><Sunny v-else /></el-icon></button>
      </footer>
    </aside>
    <main class="app-content"><RouterView /></main>
  </div>
</template>
