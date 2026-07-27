import { apiData, apiRequest } from "./client"

export type TaskStatus = "CREATED" | "RUNNING" | "FINISHED" | "TERMINATED" | "FAILED"

export interface TrainingTask {
  id: string
  status: TaskStatus
  metadata: Record<string, unknown>
  returncode?: number | null
}

interface TasksData {
  tasks: TrainingTask[]
}

export const tasksApi = {
  list: async () => (await apiData<TasksData>("/api/tasks")).tasks,
  terminate: (taskId: string) => apiRequest(`/api/tasks/terminate/${encodeURIComponent(taskId)}`),
}
