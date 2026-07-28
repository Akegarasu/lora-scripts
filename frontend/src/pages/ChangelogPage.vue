<script setup lang="ts">
const releases = [
  { version: "v2.9.0", date: "2026-07-22", items: ["Anima Fast 高分辨率 bucket 参数与训练前检查", "Anima 标准模式 LoKr 无效参数清理", "本地 WD 打标模型加载与 CUDA/CPU 回退改进", "Windows 整合包数据目录和 junction 修复"] },
  { version: "v2.8.35", date: "2026-06-28", items: ["修复 Windows 更新脚本路径、换行与 PowerShell 5.1 编码兼容", "新增 Fix-Portable-Bats.bat"] },
  { version: "v2.8.3", date: "2026-06-28", items: ["新增配置导出规范化 API", "改善整合包 Hugging Face、ModelScope 与文件选择器路径"] },
  { version: "v2.8.2", date: "2026-06-27", items: ["修复 SDXL 训练路由与离线 tokenizer", "默认 WD 打标模型开箱即用", "修复预览图和训练配置导入"] },
] as const
</script>

<template>
  <article class="content-page">
    <header class="content-hero content-hero-split"><div><span class="eyebrow">RELEASE NOTES</span><h1>更新日志</h1><p>仓库完整历史保存在 <code>CHANGELOG.md</code>，这里展示主要发行版本。</p></div><img src="/assets/changelog-banner.webp" alt="Next Trainer 更新日志"></header>
    <section class="release-list"><article v-for="release in releases" :key="release.version"><header><h2>{{ release.version }}</h2><time>{{ release.date }}</time></header><ul><li v-for="item in release.items" :key="item">{{ item }}</li></ul></article></section>
    <a class="secondary-action" href="https://github.com/wochenlong/lora-scripts-next/blob/master/CHANGELOG.md" target="_blank" rel="noreferrer">查看完整更新日志</a>
  </article>
</template>
