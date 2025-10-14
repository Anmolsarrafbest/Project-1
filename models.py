"""Pydantic models for request/response validation."""
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Union


class Attachment(BaseModel):
    """File attachment with data URI."""
    name: str
    url: str  # data:mime/type;base64,... format


class TaskRequest(BaseModel):
    """Incoming task request from IITM server."""
    email: str
    secret: str
    task: str
    round: int = Field(ge=1)
    nonce: str
    brief: str
    checks: Union[str, List[str]]
    evaluation_url: str
    attachments: Optional[List[Attachment]] = []
    
    @field_validator('checks')
    @classmethod
    def normalize_checks(cls, v):
        """Convert checks to list if it's a string."""
        if isinstance(v, str):
            return [v]
        return v


class TaskResponse(BaseModel):
    """Response sent back immediately."""
    status: str
    message: str


class EvaluationNotification(BaseModel):
    """Notification sent to evaluation server."""
    email: str
    task: str
    round: int
    nonce: str
    repo_url: str
    commit_sha: str
    pages_url: str


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str = "1.0.0"
