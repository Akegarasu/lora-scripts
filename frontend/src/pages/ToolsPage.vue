<script setup lang="ts">
import { reactive, ref } from "vue"
import { ElMessage } from "element-plus"
import { AVAILABLE_SCRIPTS, toolsApi, type ToolScript } from "../api/tools"

const script = ref<ToolScript>(AVAILABLE_SCRIPTS[0])
const rows = reactive([{ key: "", value: "" }])
const submitting = ref(false)
function addRow() { rows.push({ key: "", value: "" }) }
function removeRow(index: number) { rows.splice(index, 1); if (!rows.length) addRow() }
function parseValue(value: string): string | number | boolean {
  if (value === "true") return true
  if (value === "false") return false
  const number = Number(value)
  return value !== "" && Number.isFinite(number) ? number : value
}
async function run() {
  const args: Record<string, string | number | boolean> = {}
  for (const row of rows) {
    const key = row.key.trim().replace(/^--/, "")
    if (key) args[key] = parseValue(row.value.trim())
  }
  submitting.value = true
  try { await toolsApi.run(script.value, args); ElMessage.success("工具任务已提交") }
  catch (error) { ElMessage.error(error instanceof Error ? error.message : "任务提交失败") }
  finally { submitting.value = false }
}
</script>

<template>
  <div class="simple-page"><header><span class="eyebrow">SCRIPT TOOLS</span><h1>LoRA 脚本工具</h1><p>运行后端白名单中的模型与 LoRA 处理脚本。任务在后端后台执行。</p></header>
    <section class="settings-card"><label for="tool-script">脚本</label><select id="tool-script" v-model="script"><option v-for="name in AVAILABLE_SCRIPTS" :key="name" :value="name">{{ name }}</option></select>
      <div class="argument-heading"><strong>参数</strong><button @click="addRow">添加参数</button></div>
      <div v-for="(row, index) in rows" :key="index" class="argument-row"><input v-model="row.key" placeholder="参数名，例如 model_org" /><input v-model="row.value" placeholder="参数值" /><button aria-label="删除参数" @click="removeRow(index)">×</button></div>
      <div class="form-actions"><button class="primary-action" :disabled="submitting" @click="run">{{ submitting ? "提交中…" : "启动工具" }}</button></div>
    </section>
  </div>
</template>
