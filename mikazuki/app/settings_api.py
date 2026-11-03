from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, StrictBool


router = APIRouter()


class MCPSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: StrictBool


@router.get("/mcp")
async def get_mcp_settings(request: Request):
    return request.app.state.mcp_service.status(request)


@router.patch("/mcp")
async def update_mcp_settings(request: Request, update: MCPSettingsUpdate):
    service = request.app.state.mcp_service
    try:
        service.set_enabled(update.enabled)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=f"无法保存 MCP 设置：{exc}") from exc
    return service.status(request)
