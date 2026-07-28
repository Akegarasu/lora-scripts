// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest"
import { ApiError, apiData, apiRequest } from "./client"

afterEach(() => vi.restoreAllMocks())

function response(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" }, ...init })
}

describe("apiRequest", () => {
  it("adds JSON headers and returns successful payloads", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(response({ status: "success", data: { id: 7 } }))

    await expect(apiData<{ id: number }>("/api/example", { method: "POST", body: "{}" })).resolves.toEqual({ id: 7 })
    expect(fetchMock).toHaveBeenCalledWith("/api/example", expect.objectContaining({ headers: { "Content-Type": "application/json" } }))
  })

  it("allows pending responses only when requested", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(response({ status: "pending", message: "working" }))
    await expect(apiRequest("/api/task", { allowPending: true })).resolves.toMatchObject({ status: "pending" })

    vi.mocked(fetch).mockResolvedValue(response({ status: "pending", message: "working" }))
    await expect(apiRequest("/api/task")).rejects.toMatchObject({ status: "pending" })
  })

  it("classifies network, HTTP, invalid JSON, and missing data failures", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch")
    fetchMock.mockRejectedValueOnce(new Error("offline"))
    await expect(apiRequest("/api/offline")).rejects.toMatchObject({ status: "network" })

    fetchMock.mockResolvedValueOnce(response({ status: "fail", message: "denied" }, { status: 403 }))
    await expect(apiRequest("/api/denied")).rejects.toMatchObject({ status: "http", message: "denied" })

    fetchMock.mockResolvedValueOnce(new Response("not json", { status: 502 }))
    await expect(apiRequest("/api/broken")).rejects.toBeInstanceOf(ApiError)

    fetchMock.mockResolvedValueOnce(response({ status: "success" }))
    await expect(apiData("/api/empty")).rejects.toMatchObject({ message: "后端响应缺少 data" })
  })
})
