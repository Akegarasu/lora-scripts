<script setup lang="ts">
import { reactive } from "vue"
import { ElMessage } from "element-plus"

const STORAGE_KEY = "ui-configs"
const defaults = { tensorboard_url: "" }
let saved: Partial<typeof defaults> = {}
try { saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}") as Partial<typeof defaults> } catch { saved = {} }
const form = reactive({ ...defaults, ...saved })

function save() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify({ tensorboard_url: form.tensorboard_url.trim() }))
  ElMessage.success("设置已保存")
}
function reset() {
  Object.assign(form, defaults)
  localStorage.setItem(STORAGE_KEY, JSON.stringify(defaults))
  ElMessage.success("设置已重置")
}
</script>

<template>
  <div class="simple-page"><header><span class="eyebrow">LOCAL SETTINGS</span><h1>训练 UI 设置</h1><p>设置只保存在当前浏览器中，兼容旧版 <code>ui-configs</code>。</p></header>
    <section class="settings-card"><label for="tensorboard-url">TensorBoard URL</label><input id="tensorboard-url" v-model="form.tensorboard_url" placeholder="留空时使用 /proxy/tensorboard/" /><small>可填写独立 TensorBoard 地址；留空时继续通过后端同源代理访问。</small><div class="form-actions"><button class="primary-action" @click="save">保存设置</button><button class="secondary-action" @click="reset">全部重置</button></div></section>
  </div>
</template>
