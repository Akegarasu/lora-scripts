from pydantic import BaseModel, Field


class TaggerInterrogateRequest(BaseModel):
    path: str
    threshold: float = Field(
        default=0.35,
        ge=0,
        le=1
    )
