from pydantic import BaseModel, Field


class TaggerInterrogateRequest(BaseModel):
    path: str
    threshold: float = Field(
        default=0.35,
        ge=0,
        le=1
    )
    additional_tags: str = Field(
        default=""
    )
    exclude_tags: str = Field(
        default=""
    )
    replace_underscore: bool = True
    replace_underscore_excludes: str = Field(
        default="0_0, (o)_(o), +_+, +_-, ._., <o>_<o>, <|>_<|>, =_=, >_<, 3_3, 6_9, >_o, @_@, ^_^, o_o, u_u, x_x, |_|, ||_||"
    )
