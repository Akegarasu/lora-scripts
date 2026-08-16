from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, validator


class ValidationMessage(BaseModel):
    severity: str
    code: str
    message: str
    field: Optional[str] = None


class RuntimeDraft(BaseModel):
    gpuIds: List[str] = Field(default_factory=list)
    numCpuThreadsPerProcess: int = Field(default=8, ge=1)

    @validator("gpuIds", pre=True)
    def normalize_gpu_ids(cls, value: Any) -> Any:
        if value is None:
            return []
        if not isinstance(value, (list, tuple)):
            return value

        normalized = []
        for raw_gpu_id in value:
            if isinstance(raw_gpu_id, str):
                gpu_id = raw_gpu_id.strip()
                if gpu_id:
                    normalized.append(gpu_id)
            else:
                normalized.append(raw_gpu_id)
        return normalized

    @validator("gpuIds")
    def reject_duplicate_gpu_ids(cls, value: List[str]) -> List[str]:
        seen = set()
        for gpu_id in value:
            if "," in gpu_id or any(char.isspace() or ord(char) < 32 for char in gpu_id):
                raise ValueError(f"gpuIds contains an invalid device identifier: {gpu_id}")
            if gpu_id in seen:
                raise ValueError(f"gpuIds contains a duplicate value: {gpu_id}")
            seen.add(gpu_id)
        return value


class SimpleDatasetDraft(BaseModel):
    mode: str = "simple"
    root: Optional[str] = None
    captionExtension: str = ".txt"
    resolution: Any = Field(default_factory=lambda: [1024, 1024])
    batchSize: int = 1
    numRepeats: int = 1
    enableBucket: bool = True
    minBucketReso: int = 256
    maxBucketReso: int = 2048
    bucketResoSteps: int = 64
    bucketNoUpscale: bool = True
    shuffleCaption: bool = False
    keepTokens: int = 0


class SamplePromptDraft(BaseModel):
    prompt: str = ""
    negativePrompt: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    seed: Optional[int] = None
    steps: Optional[int] = None
    cfgScale: Optional[float] = None
    guidanceScale: Optional[float] = None


class SampleDraft(BaseModel):
    enabled: bool = False
    everyNEpochs: Optional[int] = None
    everyNSteps: Optional[int] = None
    sampler: Optional[str] = None
    prompts: List[SamplePromptDraft] = Field(default_factory=list)


class TrainDraft(BaseModel):
    trainerId: str
    name: Optional[str] = None
    modelAssets: Dict[str, Any] = Field(default_factory=dict)
    dataset: Optional[Dict[str, Any]] = None
    params: Dict[str, Any] = Field(default_factory=dict)
    runtime: RuntimeDraft = Field(default_factory=RuntimeDraft)
    sample: SampleDraft = Field(default_factory=SampleDraft)


class CompileArtifacts(BaseModel):
    draft: Optional[str] = None
    trainConfig: Optional[str] = None
    datasetConfig: Optional[str] = None
    samplePrompts: Optional[str] = None
    command: Optional[str] = None
    loggingDir: Optional[str] = None
    logPrefix: Optional[str] = None


class CompileResult(BaseModel):
    runId: Optional[str] = None
    trainerId: str
    manifestHash: str
    artifacts: CompileArtifacts = Field(default_factory=CompileArtifacts)
    command: List[str] = Field(default_factory=list)
    trainConfig: Optional[str] = None
    datasetConfig: Optional[str] = None
    samplePrompts: Optional[str] = None
    warnings: List[ValidationMessage] = Field(default_factory=list)
    errors: List[ValidationMessage] = Field(default_factory=list)
