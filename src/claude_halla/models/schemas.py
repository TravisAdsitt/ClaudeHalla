"""Pydantic input/output models for all MCP tools."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# --- Auth ---

class AuthenticateInput(BaseModel):
    username: str
    password: str


class AuthenticateOutput(BaseModel):
    token: str
    expires_at: str
    username: str


class RefreshTokenInput(BaseModel):
    token: str


class RefreshTokenOutput(BaseModel):
    token: str
    expires_at: str
    username: str


# --- Wall ---

class PostToWallInput(BaseModel):
    token: str
    content: str = Field(..., max_length=2000)
    project_key: str | None = None
    ttl_hours: int | None = None


class PostToWallOutput(BaseModel):
    post_id: str
    expires_at: str
    project_key: str | None


class RetractPostInput(BaseModel):
    token: str
    post_id: str


class RetractPostOutput(BaseModel):
    retracted: bool
    post_id: str


class WallPostItem(BaseModel):
    id: str
    username: str
    content: str
    project_key: str | None
    posted_at: str
    expires_at: str
    status: str


class ReadWallInput(BaseModel):
    token: str
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=20)
    suppress_hint: bool = False


class ReadWallOutput(BaseModel):
    posts: list[WallPostItem]
    total_active: int
    has_more: bool
    _hint: str | None = None

    model_config = {"populate_by_name": True}


class GetUserSummaryInput(BaseModel):
    token: str
    target_username: str


class GetUserSummaryOutput(BaseModel):
    active_posts: list[WallPostItem]
    recent_archived: list[dict[str, Any]]
    projects: list[dict[str, Any]]


# --- Registry ---

class RegistryEntryItem(BaseModel):
    id: str
    repo_url: str
    description: str
    added_at: str
    last_seen_at: str
    status: str


class ReadRegistryInput(BaseModel):
    token: str
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=20)
    suppress_hint: bool = False


class ReadRegistryOutput(BaseModel):
    entries: list[RegistryEntryItem]
    total_active: int
    has_more: bool
    _hint: str | None = None

    model_config = {"populate_by_name": True}


class AddToRegistryInput(BaseModel):
    token: str
    repo_url: str
    description: str = Field(..., max_length=1000)
    project_key: str | None = None


class AddToRegistryOutput(BaseModel):
    entry_id: str
    created: bool
    graduated: bool


class UpdateRegistryEntryInput(BaseModel):
    token: str
    repo_url: str
    description: str = Field(..., max_length=1000)


class UpdateRegistryEntryOutput(BaseModel):
    entry_id: str
    updated: bool
