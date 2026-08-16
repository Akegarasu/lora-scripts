from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, validator


CaptionOutputMode = Literal["tags", "caption", "hybrid"]
CaptionJobState = Literal[
    "created",
    "queued",
    "running",
    "loading",
    "generating",
    "awaiting_review",
    "committing",
    "succeeded",
    "partial",
    "failed",
    "canceling",
    "canceled",
    "interrupted",
]
CaptionItemState = Literal[
    "pending",
    "running",
    "succeeded",
    "failed",
    "skipped",
    "conflict",
    "canceled",
]

CAPTION_TERMINAL_STATES = {
    "awaiting_review",
    "succeeded",
    "partial",
    "failed",
    "canceled",
    "interrupted",
}
SAFE_CAPTION_EXTENSIONS = {".txt", ".caption", ".tags"}


class CaptionModelParam(BaseModel):
    name: str
    label: str
    description: str
    type: Literal["string", "integer", "number", "boolean", "choice", "multiline"]
    default: Any = None
    choices: Optional[List[Any]] = None
    min: Optional[float] = None
    max: Optional[float] = None
    step: Optional[float] = None
    advanced: bool = False
    required: bool = False
    placeholder: Optional[str] = None


class CaptionModelParamGroup(BaseModel):
    id: str
    title: str
    description: str = ""
    params: List[CaptionModelParam] = Field(default_factory=list)


class CaptionModelCapabilities(BaseModel):
    prompt: bool = False
    scores: bool = False
    categories: bool = False
    batch: bool = True
    languages: List[str] = Field(default_factory=lambda: ["en"])
    devices: List[str] = Field(default_factory=lambda: ["cpu", "cuda"])


class CaptionModelSummary(BaseModel):
    id: str
    title: str
    description: str
    family: str
    engine: str
    provider: Literal["local-onnx", "local-transformers", "remote"]
    repoId: Optional[str] = None
    outputModes: List[CaptionOutputMode]
    defaultOutputMode: CaptionOutputMode
    status: Literal["ready", "downloadable", "unavailable", "misconfigured"]
    statusReason: Optional[str] = None
    missingDependencies: List[str] = Field(default_factory=list)
    capabilities: CaptionModelCapabilities
    paramGroups: List[CaptionModelParamGroup] = Field(default_factory=list)
    recommendedVramGb: Optional[float] = None
    license: Optional[str] = None
    homepage: Optional[str] = None
    minTransformers: Optional[str] = None
    gated: bool = False
    requiresHfToken: bool = False
    trustRemoteCode: bool = False
    warnings: List[str] = Field(default_factory=list)
    experimental: bool = False


class CaptionModelsResponse(BaseModel):
    models: List[CaptionModelSummary] = Field(default_factory=list)
    defaultModelId: str


class CaptionDatasetInspectRequest(BaseModel):
    root: Literal["train", "datasets", "workspace"] = "train"
    path: str = ""
    recursive: bool = True
    captionExtension: str = ".txt"
    maxImages: int = Field(default=10_000, ge=1, le=50_000)
    initialLimit: int = Field(default=100, ge=1, le=200)

    @validator("captionExtension")
    def validate_caption_extension(cls, value: str) -> str:
        extension = value.strip()
        if not extension.startswith("."):
            extension = f".{extension}"
        extension = extension.lower()
        if extension not in SAFE_CAPTION_EXTENSIONS:
            allowed = "、".join(sorted(SAFE_CAPTION_EXTENSIONS))
            raise ValueError(f"captionExtension 仅允许安全的文本扩展名：{allowed}")
        return extension


class CaptionDatasetItem(BaseModel):
    id: str
    name: str
    relativePath: str
    width: Optional[int] = None
    height: Optional[int] = None
    captionExists: bool = False
    captionText: str = ""
    captionTruncated: bool = False
    writable: bool = True
    error: Optional[str] = None
    errorCode: Optional[str] = None
    thumbnailUrl: str


class CaptionDatasetSummary(BaseModel):
    id: str
    root: str
    path: str
    recursive: bool
    captionExtension: str
    total: int
    withCaption: int
    withoutCaption: int
    truncated: bool = False
    createdAt: str


class CaptionDatasetInspectResponse(BaseModel):
    dataset: CaptionDatasetSummary
    items: List[CaptionDatasetItem] = Field(default_factory=list)


class CaptionDatasetItemsResponse(BaseModel):
    datasetId: str
    total: int
    offset: int
    limit: int
    items: List[CaptionDatasetItem] = Field(default_factory=list)


class CaptionTextUpdateRequest(BaseModel):
    text: str = Field(default="", max_length=100_000)
    backupExisting: bool = True


class CaptionPromptOptions(BaseModel):
    instruction: str = Field(
        default="Describe this image accurately for image-generation training.",
        max_length=8_000,
    )
    language: str = Field(default="en", max_length=32)


class CaptionPostprocessOptions(BaseModel):
    additionalTags: List[str] = Field(default_factory=list)
    excludeTags: List[str] = Field(default_factory=list)
    prefix: str = Field(default="", max_length=4_000)
    suffix: str = Field(default="", max_length=4_000)
    separator: str = Field(default=", ", max_length=32)
    deduplicate: bool = True
    replaceUnderscore: bool = True
    replaceUnderscoreExcludes: List[str] = Field(default_factory=list)
    escapeTags: bool = False
    includeConfidence: bool = False


class CaptionOutputOptions(BaseModel):
    stageBeforeWrite: bool = False
    conflictPolicy: Literal["skip", "fill_empty", "overwrite", "prepend", "append"] = "skip"
    backupExisting: bool = True
    saveRawResult: bool = False


class CaptionRuntimeOptions(BaseModel):
    device: Literal["auto", "cpu", "cuda"] = "auto"
    dtype: Literal["auto", "float32", "float16", "bfloat16"] = "auto"
    batchSize: int = Field(default=1, ge=1, le=64)
    keepModelLoaded: bool = False


class CaptionJobCreateRequest(BaseModel):
    name: Optional[str] = Field(default=None, max_length=120)
    datasetId: str
    itemIds: Optional[List[str]] = None
    modelId: str
    outputMode: CaptionOutputMode
    params: Dict[str, Any] = Field(default_factory=dict)
    prompt: CaptionPromptOptions = Field(default_factory=CaptionPromptOptions)
    postprocess: CaptionPostprocessOptions = Field(default_factory=CaptionPostprocessOptions)
    output: CaptionOutputOptions = Field(default_factory=CaptionOutputOptions)
    runtime: CaptionRuntimeOptions = Field(default_factory=CaptionRuntimeOptions)


class CaptionTag(BaseModel):
    text: str
    score: Optional[float] = None
    category: Optional[str] = None


class CaptionPrediction(BaseModel):
    text: str
    tags: List[CaptionTag] = Field(default_factory=list)
    raw: Optional[Dict[str, Any]] = None


class CaptionJobSummary(BaseModel):
    id: str
    name: Optional[str] = None
    modelId: str
    modelTitle: str
    outputMode: CaptionOutputMode
    state: CaptionJobState
    reviewMode: bool = False
    detailsState: Literal["available", "compacted", "expired"] = "available"
    message: str = ""
    revision: int = 0
    datasetId: str
    logPath: str
    total: int = 0
    processed: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0
    conflicts: int = 0
    written: int = 0
    createdAt: str
    startedAt: Optional[str] = None
    endedAt: Optional[str] = None
    errorMessage: Optional[str] = None


class CaptionJobListResponse(BaseModel):
    jobs: List[CaptionJobSummary] = Field(default_factory=list)


class CaptionJobItem(BaseModel):
    id: str
    index: int
    name: str
    relativePath: str
    state: CaptionItemState
    existingText: str = ""
    generatedText: str = ""
    finalText: str = ""
    tags: List[CaptionTag] = Field(default_factory=list)
    error: Optional[str] = None
    written: bool = False
    edited: bool = False
    elapsedMs: Optional[int] = None
    thumbnailUrl: str


class CaptionJobItemsResponse(BaseModel):
    jobId: str
    total: int
    offset: int
    limit: int
    items: List[CaptionJobItem] = Field(default_factory=list)


class CaptionJobItemUpdateRequest(BaseModel):
    finalText: str = Field(default="", max_length=100_000)


class CaptionCommitRequest(BaseModel):
    itemIds: Optional[List[str]] = None
    conflictPolicy: Optional[Literal["skip", "fill_empty", "overwrite", "prepend", "append"]] = None
    backupExisting: Optional[bool] = None
