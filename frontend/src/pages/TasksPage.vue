<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted } from "vue"
import { ElMessage, ElMessageBox } from "element-plus"
import { Refresh } from "@element-plus/icons-vue"
import { storeToRefs } from "pinia"
import { useTasksStore } from "../stores/tasks"
import type { TaskStatus, TrainingTask } from "../api/tasks"

const store = useTasksStore()
const { tasks, runningTasks, loading, error, terminatingId } = storeToRefs(store)
const orderedTasks = computed(() => [...tasks.value].reverse())
let timer: number | undefined

const statusLabels: Record<TaskStatus, string> = {
  CREATED: "已创建",
  RUNNING: "运行中",
  FINISHED: "已完成",
  TERMINATED: "已终止",
  FAILED: "失败",
}

function taskName(task: TrainingTask) {
  return String(task.metadata.output_name || task.metadata.trainer_file || task.metadata.backend || "训练任务")
}

function taskDetail(task: TrainingTask) {
  return String(task.metadata.config_path || task.metadata.command || "暂无任务描述")
}

async function terminate(task: TrainingTask) {
  try {
    await ElMessageBox.confirm(`确定要停止任务 ${task.id} 吗？`, "终止训练", {
      confirmButtonText: "停止任务",
      cancelButtonText: "取消",
      type: "warning",
    })
    await store.terminate(task.id)
    ElMessage.success("停止任务成功")
  } catch (caught) {
    if (caught !== "cancel" && caught !== "close") {
      ElMessage.error(caught instanceof Error ? caught.message : "停止任务失败")
    }
  }
}

onMounted(async () => {
  await store.refresh()
  timer = window.setInterval(() => store.refresh({ silent: true }), 2000)
})

onBeforeUnmount(() => window.clearInterval(timer))
</script>

<template>
  <div class="tasks-page">
    <header class="tasks-header">
      <div><span class="eyebrow">TASK CONTROL</span><h1>训练任务</h1><p>查看当前服务会话中的训练任务、运行状态和日志。</p></div>
      <button class="refresh-button" :disabled="loading" @click="store.refresh()"><el-icon><Refresh /></el-icon>刷新</button>
    </header>

    <section class="task-summary">
      <div><strong>{{ runningTasks.length }}</strong><span>运行中</span></div>
      <div><strong>{{ tasks.length }}</strong><span>本次会话任务</span></div>
      <div><strong>2s</strong><span>自动刷新</span></div>
    </section>

    <div v-if="error" class="task-error"><strong>无法读取任务</strong><span>{{ error }}</span><button @click="store.refresh()">重试</button></div>
    <div v-else-if="loading && !tasks.length" class="task-empty">正在读取任务列表…</div>
    <div v-else-if="!tasks.length" class="task-empty"><strong>当前没有训练任务</strong><span>从训练参数页提交任务后，将在这里显示状态和日志入口。</span></div>

    <section v-else class="task-list">
      <article v-for="task in orderedTasks" :key="task.id" class="task-card" :data-status="task.status.toLowerCase()">
        <div class="task-main">
          <div class="task-title-row"><span class="task-status">{{ statusLabels[task.status] || task.status }}</span><h2>{{ taskName(task) }}</h2></div>
          <code>{{ task.id }}</code><p :title="taskDetail(task)">{{ taskDetail(task) }}</p>
        </div>
        <div class="task-meta"><span>返回码</span><strong>{{ task.returncode ?? "-" }}</strong></div>
        <div class="task-actions">
          <a :href="`/train-log?task_id=${encodeURIComponent(task.id)}`" target="_blank" rel="noreferrer">查看日志</a>
          <button v-if="task.status === 'RUNNING'" :disabled="terminatingId === task.id" @click="terminate(task)">{{ terminatingId === task.id ? "停止中…" : "终止训练" }}</button>
        </div>
      </article>
    </section>
  </div>
</template>
