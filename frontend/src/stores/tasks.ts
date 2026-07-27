import { computed, ref } from "vue"
import { defineStore } from "pinia"
import { tasksApi, type TrainingTask } from "../api/tasks"

export const useTasksStore = defineStore("tasks", () => {
  const tasks = ref<TrainingTask[]>([])
  const loading = ref(false)
  const error = ref("")
  const terminatingId = ref("")
  const runningTasks = computed(() => tasks.value.filter((task) => task.status === "RUNNING"))

  async function refresh(options: { silent?: boolean } = {}) {
    if (!options.silent) loading.value = true
    try {
      tasks.value = await tasksApi.list()
      error.value = ""
    } catch (caught) {
      error.value = caught instanceof Error ? caught.message : "任务列表加载失败"
    } finally {
      loading.value = false
    }
  }

  async function terminate(taskId: string) {
    terminatingId.value = taskId
    try {
      await tasksApi.terminate(taskId)
      await refresh({ silent: true })
    } finally {
      terminatingId.value = ""
    }
  }

  return { tasks, runningTasks, loading, error, terminatingId, refresh, terminate }
})
