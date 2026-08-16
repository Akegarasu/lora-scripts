from __future__ import annotations

from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field, root_validator, validator

from mikazuki.captioning.models import SAFE_CAPTION_EXTENSIONS


TagEditorItemState = Literal["all", "with", "missing", "empty", "errors", "duplicate"]
TagEditorSort = Literal["path_asc", "path_desc", "caption_asc", "modified_desc"]
TagEditorChangeState = Literal[
    "previewed",
    "queued",
    "applying",
    "completed",
    "partial",
    "failed",
    "rolling_back",
    "rolled_back",
    "rollback_partial",
    "interrupted",
]


class StrictModel(BaseModel):
    class Config:
        extra = "forbid"


class TagEditorInspectRequest(StrictModel):
    root: Literal["train", "datasets", "workspace"] = "train"
    path: str = Field(default="", max_length=4_096)
    recursive: bool = True
    captionExtension: str = ".txt"
    maxImages: int = Field(default=10_000, ge=1, le=50_000)
    initialLimit: int = Field(default=100, ge=1, le=200)

    @validator("captionExtension")
    def validate_caption_extension(cls, value: str) -> str:
        extension = value.strip().lower()
        if not extension.startswith("."):
            extension = f".{extension}"
        if extension not in SAFE_CAPTION_EXTENSIONS:
            allowed = "、".join(sorted(SAFE_CAPTION_EXTENSIONS))
            raise ValueError(f"Caption 后缀仅允许安全文本类型：{allowed}")
        return extension


class TagEditorTagCount(StrictModel):
    text: str
    count: int


class TagEditorDatasetSummary(StrictModel):
    id: str
    revision: str
    root: str
    path: str
    recursive: bool
    captionExtension: str
    total: int
    withCaption: int
    missing: int
    empty: int
    errors: int
    duplicates: int
    truncated: bool = False
    createdAt: str


class TagEditorDatasetItem(StrictModel):
    id: str
    name: str
    relativePath: str
    width: Optional[int] = None
    height: Optional[int] = None
    captionExists: bool = False
    captionText: str = ""
    captionPreviewTruncated: bool = False
    sourceTruncated: bool = False
    writable: bool = True
    error: Optional[str] = None
    errorCode: Optional[str] = None
    duplicateCount: int = 0
    tags: List[str] = Field(default_factory=list)
    thumbnailUrl: str


class TagEditorItemDetail(TagEditorDatasetItem):
    pass


class TagEditorInspectResponse(StrictModel):
    dataset: TagEditorDatasetSummary
    items: List[TagEditorDatasetItem] = Field(default_factory=list)
    commonTags: List[TagEditorTagCount] = Field(default_factory=list)


class TagEditorItemsResponse(StrictModel):
    datasetId: str
    revision: str
    total: int
    offset: int
    limit: int
    items: List[TagEditorDatasetItem] = Field(default_factory=list)


class TagEditorScope(StrictModel):
    mode: Literal["include", "filter"]
    includeIds: List[str] = Field(default_factory=list, max_items=5_000)
    query: str = Field(default="", max_length=200)
    state: TagEditorItemState = "all"
    exclusions: List[str] = Field(default_factory=list, max_items=5_000)

    @root_validator(skip_on_failure=True)
    def validate_scope(cls, values):
        mode = values.get("mode")
        include_ids = values.get("includeIds") or []
        exclusions = values.get("exclusions") or []
        if len(include_ids) != len(set(include_ids)) or len(exclusions) != len(set(exclusions)):
            raise ValueError("作用域中的项目 id 不能重复")
        if mode == "include":
            if not include_ids:
                raise ValueError("显式选择作用域至少需要一个项目")
            if exclusions or values.get("query") or values.get("state") != "all":
                raise ValueError("显式选择作用域不能同时携带筛选条件或排除项")
        elif include_ids:
            raise ValueError("筛选作用域不能同时携带显式选择项目")
        return values


class TagEditorSetOperation(StrictModel):
    type: Literal["set"]
    text: str = Field(default="", max_length=100_000)


class TagEditorAddOperation(StrictModel):
    type: Literal["add"]
    mode: Literal["tags", "text"] = "tags"
    values: List[str] = Field(min_items=1, max_items=1_000)
    position: Literal["start", "end"] = "end"
    separator: str = Field(default=", ", min_length=1, max_length=32)
    deduplicate: bool = True

    @validator("values")
    def validate_values(cls, value: List[str]) -> List[str]:
        normalized = [item.strip() for item in value if item.strip()]
        if not normalized:
            raise ValueError("至少提供一个非空内容")
        if any(len(value) > 2_000 for value in normalized):
            raise ValueError("单个新增内容不能超过 2,000 个字符")
        return normalized


class TagEditorRemoveOperation(StrictModel):
    type: Literal["remove"]
    mode: Literal["tags", "text"] = "tags"
    values: List[str] = Field(min_items=1, max_items=1_000)
    matchCase: bool = False
    wholeWord: bool = True
    separator: str = Field(default=", ", min_length=1, max_length=32)

    @validator("values")
    def validate_values(cls, value: List[str]) -> List[str]:
        normalized = [item.strip() for item in value if item.strip()]
        if not normalized:
            raise ValueError("至少提供一个非空内容")
        if any(len(value) > 2_000 for value in normalized):
            raise ValueError("单个删除内容不能超过 2,000 个字符")
        return normalized


class TagEditorReplaceOperation(StrictModel):
    type: Literal["replace"]
    search: str = Field(min_length=1, max_length=500)
    replacement: str = Field(default="", max_length=10_000)
    useRegex: bool = False
    matchCase: bool = False
    wholeWord: bool = False


class TagEditorNormalizeOperation(StrictModel):
    type: Literal["normalize"]
    mode: Literal["tags", "text"] = "tags"
    separator: str = Field(default=", ", min_length=1, max_length=32)
    trim: bool = True
    deduplicate: bool = True
    sort: Literal["none", "alphabetical", "natural"] = "none"
    caseSensitive: bool = False
    replaceUnderscore: bool = False


TagEditorOperation = Union[
    TagEditorSetOperation,
    TagEditorAddOperation,
    TagEditorRemoveOperation,
    TagEditorReplaceOperation,
    TagEditorNormalizeOperation,
]


class TagEditorPreviewRequest(StrictModel):
    revision: str
    scope: TagEditorScope
    operations: List[TagEditorOperation] = Field(min_items=1, max_items=20)
    sampleLimit: int = Field(default=30, ge=1, le=50)


class TagEditorDiff(StrictModel):
    itemId: str
    name: str
    relativePath: str
    before: str
    after: str
    beforeTruncated: bool = False
    afterTruncated: bool = False


class TagEditorPreviewIssue(StrictModel):
    itemId: str
    name: str
    relativePath: str
    error: str


class TagEditorChangeSetSummary(StrictModel):
    id: str
    datasetId: str
    datasetPath: str = ""
    revision: str
    resultRevision: Optional[str] = None
    state: TagEditorChangeState
    message: str = ""
    matched: int = 0
    changed: int = 0
    unchanged: int = 0
    conflicts: int = 0
    failed: int = 0
    applied: int = 0
    rolledBack: int = 0
    rollbackConflicts: int = 0
    backupExisting: bool = True
    canRollback: bool = False
    createdAt: str
    startedAt: Optional[str] = None
    endedAt: Optional[str] = None


class TagEditorPreviewResponse(TagEditorChangeSetSummary):
    diffs: List[TagEditorDiff] = Field(default_factory=list)
    issues: List[TagEditorPreviewIssue] = Field(default_factory=list)


class TagEditorApplyRequest(StrictModel):
    changeSetId: str = Field(max_length=128)
    revision: str = Field(max_length=128)
    backupExisting: bool = True


class TagEditorChangeSetListResponse(StrictModel):
    changes: List[TagEditorChangeSetSummary] = Field(default_factory=list)


class TagEditorTagSuggestionsResponse(StrictModel):
    datasetId: str
    query: str
    suggestions: List[TagEditorTagCount] = Field(default_factory=list)


class TagEditorChangeResult(StrictModel):
    itemId: str
    relativePath: str
    state: Literal["applied", "conflict", "failed", "rolled_back", "rollback_conflict"]
    error: Optional[str] = None


class TagEditorChangeResultsResponse(StrictModel):
    changeSetId: str
    total: int
    offset: int
    limit: int
    items: List[TagEditorChangeResult] = Field(default_factory=list)
