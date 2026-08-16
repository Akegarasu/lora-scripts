from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from mikazuki.compiler.models import CompileResult


TERMINAL_STATES = {"succeeded", "failed", "terminated", "canceled"}


class JobRecord(BaseModel):
    id: str
    runId: str
    trainerId: str
    name: Optional[str] = None
    state: str = "created"
    command: List[str] = Field(default_factory=list)
    env: Dict[str, str] = Field(default_factory=dict)
    artifacts: Dict[str, str] = Field(default_factory=dict)
    logPath: Optional[str] = None
    createdAt: str
    startedAt: Optional[str] = None
    endedAt: Optional[str] = None
    exitCode: Optional[int] = None
    errorMessage: Optional[str] = None


class JobListResponse(BaseModel):
    jobs: List[JobRecord] = Field(default_factory=list)


class JobStartResult(BaseModel):
    job: Optional[JobRecord] = None
    compile: CompileResult


class JobLogResponse(BaseModel):
    jobId: str
    cursor: int = 0
    lines: List[str] = Field(default_factory=list)
