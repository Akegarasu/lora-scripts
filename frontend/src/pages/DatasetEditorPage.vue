<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue"
import { ElMessage, ElMessageBox } from "element-plus"
import { datasetApi, type ChangedItem, type DatasetHistory, type DatasetItem } from "../api/dataset"

const QUICK_TAGS_KEY = "dataset-editor-quick-tags"
const PAGE_SIZE_KEY = "dataset-editor-page-size"
const path = ref("")
const root = ref("")
const items = ref<DatasetItem[]>([])
const tags = ref<Array<{ tag: string; count: number }>>([])
const categories = ref<Array<{ name: string; value: string; count: number }>>([])
const category = ref("")
const query = ref("")
const selected = ref("")
const selectedPaths = ref(new Set<string>())
const lastSelectedIndex = ref<number>()
const caption = ref("")
const append = ref("")
const remove = ref("")
const replaceFrom = ref("")
const replaceTo = ref("")
const clean = ref(false)
const sort = ref(false)
const underscoreToSpace = ref(false)
const stripEscapeChars = ref(false)
const loading = ref(false)
const quickTag = ref("")
const quickTags = ref<string[]>([])
const page = ref(1)
const pageSize = ref(Number(localStorage.getItem(PAGE_SIZE_KEY)) || 48)
const historyOpen = ref(false)
const sessionHistory = ref<DatasetHistory>({ can_undo: false, can_redo: false, changes: [] })

const filtered = computed(() => items.value.filter((item) =>
  (!category.value || item.category === category.value) &&
  (!query.value || item.caption.toLowerCase().includes(query.value.toLowerCase()) || item.name.toLowerCase().includes(query.value.toLowerCase())),
))
const pageCount = computed(() => Math.max(1, Math.ceil(filtered.value.length / pageSize.value)))
const paged = computed(() => filtered.value.slice((page.value - 1) * pageSize.value, page.value * pageSize.value))
const current = computed(() => items.value.find((item) => item.relative_path === selected.value))
const targets = computed(() => selectedPaths.value.size ? items.value.filter((item) => selectedPaths.value.has(item.relative_path)) : filtered.value)
const popularTags = computed(() => tags.value.slice(0, 24))

function choose(item: DatasetItem, event?: MouseEvent) {
  selected.value = item.relative_path
  caption.value = item.caption
  if (!event) return
  const index = filtered.value.findIndex((candidate) => candidate.relative_path === item.relative_path)
  const next = new Set(event.ctrlKey || event.metaKey || event.shiftKey ? selectedPaths.value : [])
  if (event.shiftKey && lastSelectedIndex.value !== undefined) {
    const [start, end] = [lastSelectedIndex.value, index].sort((a, b) => a - b)
    filtered.value.slice(start, end + 1).forEach((candidate) => next.add(candidate.relative_path))
  } else if ((event.ctrlKey || event.metaKey) && next.has(item.relative_path)) next.delete(item.relative_path)
  else next.add(item.relative_path)
  selectedPaths.value = next
  lastSelectedIndex.value = index
}

function apply(changes: ChangedItem[]) {
  const map = new Map(changes.map((item) => [item.image, item]))
  items.value = items.value.map((item) => {
    const change = map.get(item.relative_path)
    return change ? { ...item, caption: change.caption, tags: change.tags, caption_exists: change.caption_exists } : item
  })
  if (current.value) caption.value = current.value.caption
  rebuildTags()
}

function rebuildTags() {
  const counts = new Map<string, number>()
  items.value.forEach((item) => item.tags.forEach((tag) => counts.set(tag, (counts.get(tag) || 0) + 1)))
  tags.value = [...counts].map(([tag, count]) => ({ tag, count })).sort((a, b) => b.count - a.count || a.tag.localeCompare(b.tag))
}

async function refreshHistory() {
  if (root.value) sessionHistory.value = await datasetApi.history(root.value)
}

async function scan() {
  if (!path.value.trim()) return
  loading.value = true
  try {
    const data = await datasetApi.scan(path.value)
    root.value = data.root
    path.value = data.root
    items.value = data.items
    tags.value = data.tags.sort((a, b) => b.count - a.count)
    categories.value = data.categories
    selectedPaths.value = new Set()
    page.value = 1
    if (data.items[0]) choose(data.items[0])
    await refreshHistory()
    ElMessage.success(`已加载 ${data.total} 张图片`)
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : "扫描失败") }
  finally { loading.value = false }
}

async function save() {
  if (!current.value) return
  try {
    apply([await datasetApi.save(root.value, current.value.relative_path, caption.value)])
    await refreshHistory()
    ElMessage.success("Caption 已保存")
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : "保存失败") }
}

function splitTags(value: string) { return value.split(/[,，\n]/).map((item) => item.trim()).filter(Boolean) }

async function batch() {
  if (!targets.value.length) return
  try {
    await ElMessageBox.confirm(`将修改 ${targets.value.length} 张图片，是否继续？`, selectedPaths.value.size ? "批量编辑已选图片" : "批量编辑当前筛选")
    const replacements = replaceFrom.value.trim() ? [{ from: replaceFrom.value.trim(), to: replaceTo.value.trim() }] : []
    const data = await datasetApi.batch({
      root: root.value, images: targets.value.map((item) => item.relative_path), append: splitTags(append.value), remove: splitTags(remove.value),
      replace: replacements, clean: clean.value, sort: sort.value, underscore_to_space: underscoreToSpace.value, strip_escape_chars: stripEscapeChars.value,
    })
    apply(data.items)
    await refreshHistory()
    ElMessage.success(`已修改 ${data.changed} 张图片`)
  } catch (error) { if (error !== "cancel" && error !== "close") ElMessage.error(error instanceof Error ? error.message : "批量编辑失败") }
}

async function changeHistory(kind: "undo" | "redo") {
  try {
    const data = await datasetApi[kind](root.value)
    apply(data.items)
    await refreshHistory()
    ElMessage.success(data.changed ? (kind === "undo" ? "已撤回" : "已重做") : "没有可执行的历史操作")
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : "操作失败") }
}

function togglePageSelection() {
  const next = new Set(selectedPaths.value)
  const allSelected = paged.value.every((item) => next.has(item.relative_path))
  paged.value.forEach((item) => allSelected ? next.delete(item.relative_path) : next.add(item.relative_path))
  selectedPaths.value = next
}

function appendQuickTag(tag: string) {
  const next = new Set(splitTags(append.value))
  next.add(tag)
  append.value = [...next].join(", ")
}

function addQuickTag() {
  const value = quickTag.value.trim()
  if (!value || quickTags.value.includes(value)) return
  quickTags.value.push(value)
  quickTag.value = ""
  localStorage.setItem(QUICK_TAGS_KEY, JSON.stringify(quickTags.value))
}

function removeQuickTag(tag: string) {
  quickTags.value = quickTags.value.filter((item) => item !== tag)
  localStorage.setItem(QUICK_TAGS_KEY, JSON.stringify(quickTags.value))
}

watch([category, query, pageSize], () => { page.value = 1; localStorage.setItem(PAGE_SIZE_KEY, String(pageSize.value)) })
watch(pageCount, (count) => { if (page.value > count) page.value = count })
onMounted(() => {
  try { quickTags.value = JSON.parse(localStorage.getItem(QUICK_TAGS_KEY) || "[]") }
  catch { quickTags.value = [] }
})
</script>

<template>
  <div class="dataset-page">
    <aside class="dataset-side">
      <span class="eyebrow">DATASET EDITOR</span><h1>标签编辑器</h1>
      <label>数据集目录<input v-model="path" @keyup.enter="scan"></label>
      <button class="primary-action" :disabled="loading" @click="scan">{{ loading ? "扫描中…" : "扫描数据集" }}</button>
      <label>分类<select v-model="category"><option value="">全部</option><option v-for="item in categories" :key="item.value" :value="item.value">{{ item.name }} ({{ item.count }})</option></select></label>
      <label>Caption / 文件名筛选<input v-model="query"></label>
      <div class="batch-box"><strong>批量编辑 {{ selectedPaths.size ? `已选 ${selectedPaths.size} 张` : `筛选结果 ${filtered.length} 张` }}</strong><input v-model="append" placeholder="追加 tag，逗号分隔"><input v-model="remove" placeholder="删除 tag，逗号分隔"><div class="replace-row"><input v-model="replaceFrom" placeholder="替换前"><input v-model="replaceTo" placeholder="替换后"></div><label><input v-model="clean" type="checkbox">清理分隔符、空白和重复</label><label><input v-model="underscoreToSpace" type="checkbox">下划线转空格</label><label><input v-model="stripEscapeChars" type="checkbox">清理转义字符</label><label><input v-model="sort" type="checkbox">按字母排序</label><button @click="batch">应用批量操作</button></div>
      <div class="quick-tag-box"><strong>快捷 tag</strong><div><button v-for="item in quickTags" :key="item" @click="appendQuickTag(item)" @contextmenu.prevent="removeQuickTag(item)">{{ item }}</button><button v-for="item in popularTags" :key="item.tag" class="suggested" @click="appendQuickTag(item.tag)">{{ item.tag }} <small>{{ item.count }}</small></button></div><span><input v-model="quickTag" placeholder="添加快捷 tag" @keyup.enter="addQuickTag"><button @click="addQuickTag">添加</button></span><small>右键删除自定义快捷 tag</small></div>
    </aside>
    <main class="dataset-gallery">
      <header><strong>{{ filtered.length }} / {{ items.length }} 张，已选 {{ selectedPaths.size }} 张</strong><div><button :disabled="!root" @click="togglePageSelection">选中/取消本页</button><button :disabled="!sessionHistory.can_undo" @click="changeHistory('undo')">撤回</button><button :disabled="!sessionHistory.can_redo" @click="changeHistory('redo')">重做</button><button :disabled="!root" @click="historyOpen = true">历史</button></div></header>
      <div class="image-grid"><button v-for="item in paged" :key="item.relative_path" :class="{ active: selected === item.relative_path, checked: selectedPaths.has(item.relative_path) }" @click="choose(item, $event)"><i v-if="selectedPaths.has(item.relative_path)">✓</i><img :src="item.image_url" :alt="item.name" loading="lazy"><span>{{ item.name }}</span></button></div>
      <footer class="dataset-pager"><button :disabled="page === 1" @click="page = 1">首页</button><button :disabled="page === 1" @click="page--">上一页</button><span>{{ page }} / {{ pageCount }}</span><button :disabled="page === pageCount" @click="page++">下一页</button><button :disabled="page === pageCount" @click="page = pageCount">末页</button><select v-model.number="pageSize"><option v-for="size in [24,48,96,192]" :key="size" :value="size">{{ size }} / 页</option></select></footer>
    </main>
    <aside class="caption-panel"><div v-if="current"><img :src="current.image_url" :alt="current.name"><strong>{{ current.relative_path }}</strong><textarea v-model="caption" rows="10"></textarea><div class="caption-tags"><button v-for="tag in current.tags" :key="tag" @click="appendQuickTag(tag)">{{ tag }}</button></div><button class="primary-action" @click="save">保存 Caption</button></div><p v-else>扫描并选择图片后开始编辑。</p></aside>
  </div>
  <el-dialog v-model="historyOpen" title="会话编辑历史" width="min(820px, 94vw)"><div class="dataset-history"><article v-for="change in sessionHistory.changes" :key="`${change.label}-${change.items[0]?.image}`"><header><strong>{{ change.label }}</strong><span>{{ change.count }} 张</span></header><details><summary>查看明细</summary><div v-for="item in change.items" :key="item.image"><code>{{ item.image }}</code><del>{{ item.before || '（无 caption）' }}</del><ins>{{ item.after || '（无 caption）' }}</ins></div></details></article><p v-if="!sessionHistory.changes.length">当前会话暂无编辑记录</p></div></el-dialog>
</template>
