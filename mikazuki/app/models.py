from pydantic import BaseModel, Field


class TaggerInterrogateRequest(BaseModel):
    path: str
    interrogator_model: str = Field(
        default="wd14-convnextv2-v2"
    )
    threshold: float = Field(
        default=0.35,
        ge=0,
        le=1
    )
    additional_tags: str = ""
    exclude_tags: str = ""
    escape_tag: bool = True
    batch_output_action_on_conflict: str = "ignore"
    replace_underscore: bool = True
    replace_underscore_excludes: str = Field(
        default="0_0, (o)_(o), +_+, +_-, ._., <o>_<o>, <|>_<|>, =_=, >_<, 3_3, 6_9, >_o, @_@, ^_^, o_o, u_u, x_x, |_|, ||_||"
    )
