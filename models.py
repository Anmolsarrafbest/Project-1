"""Pydantic models for request/response validation."""
from pydantic import BaseModel, Field
from typing import List, Optional


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
    checks: List[str]
    evaluation_url: str
    attachments: Optional[List[Attachment]] = []


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
