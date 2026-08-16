from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ParamSource(BaseModel):
    script: Optional[str] = None
    module: Optional[str] = None
    function: Optional[str] = None


class ParamDefinition(BaseModel):
    name: str
    flags: List[str] = Field(default_factory=list)
    type: str = "string"
    itemType: Optional[str] = None
    default: Any = None
    effectiveDefault: Any = None
    choices: Optional[List[Any]] = None
    nargs: Any = None
    action: Optional[str] = None
    required: bool = False
    help: str = ""
    source: Optional[ParamSource] = None

    label: Optional[str] = None
    description: Optional[str] = None
    group: str = "raw"
    priority: str = "raw"
    control: Optional[str] = None
    fileKind: Optional[str] = None
    min: Optional[float] = None
    max: Optional[float] = None
    step: Optional[float] = None
    precision: Optional[int] = None
    placeholder: Optional[str] = None
    omitIfZero: bool = False
    deprecated: bool = False
    sensitive: bool = False
    advanced: bool = False
    hidden: bool = False
    rules: List[Dict[str, Any]] = Field(default_factory=list)
    extra: Dict[str, Any] = Field(default_factory=dict)


class ParamGroup(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    order: int = 100


class TrainerDefinition(BaseModel):
    id: str
    title: str
    family: str
    task: str
    script: str
    status: str = "stable"
    supportsDatasetConfig: bool = True
    supportsSamplePrompts: bool = True
    defaultNetworkModule: Optional[str] = None
    datasetDefaults: Dict[str, Any] = Field(default_factory=dict)
    params: Dict[str, ParamDefinition] = Field(default_factory=dict)
    groups: List[ParamGroup] = Field(default_factory=list)
    manifestHash: Optional[str] = None


class TrainerSummary(BaseModel):
    id: str
    title: str
    family: str
    task: str
    script: str
    status: str
    datasetDefaults: Dict[str, Any] = Field(default_factory=dict)


class CatalogManifest(BaseModel):
    schemaVersion: int = 1
    generatedAt: str
    scriptsRoot: str
    manifestHash: Optional[str] = None
    sharedParams: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    trainers: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
