export type ApiStatus = "success" | "fail" | "pending" | "error"

export interface ApiResponse<T> {
  status: ApiStatus
  message?: string | null
  data?: T | null
}

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: ApiStatus | "http" | "network",
    public readonly response?: ApiResponse<unknown>,
  ) {
    super(message)
    this.name = "ApiError"
  }
}

export interface ApiRequestOptions extends RequestInit {
  allowPending?: boolean
}

export async function apiRequest<T>(path: string, options: ApiRequestOptions = {}): Promise<ApiResponse<T>> {
  const { allowPending = false, headers, ...requestOptions } = options
  let response: Response

  try {
    response = await fetch(path, {
      ...requestOptions,
      headers: {
        ...(requestOptions.body ? { "Content-Type": "application/json" } : {}),
        ...headers,
      },
    })
  } catch (error) {
    throw new ApiError(error instanceof Error ? error.message : "无法连接到后端", "network")
  }

  let payload: ApiResponse<T>
  try {
    payload = await response.json() as ApiResponse<T>
  } catch {
    throw new ApiError(`后端返回了无法解析的响应（HTTP ${response.status}）`, "http")
  }

  if (!response.ok) {
    throw new ApiError(payload.message || `请求失败（HTTP ${response.status}）`, "http", payload)
  }
  if (payload.status !== "success" && !(allowPending && payload.status === "pending")) {
    throw new ApiError(payload.message || "请求失败", payload.status, payload)
  }
  return payload
}

export async function apiData<T>(path: string, options?: ApiRequestOptions): Promise<T> {
  const response = await apiRequest<T>(path, options)
  if (response.data == null) throw new ApiError("后端响应缺少 data", response.status, response)
  return response.data
}
