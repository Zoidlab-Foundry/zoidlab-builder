"""Workflow JSON schema — the standardized DAG definition the whole platform
compiles to. Nodes + edges; each node has a type and a free-form `data` config."""
from typing import Any, Optional
from pydantic import BaseModel, Field


class Position(BaseModel):
    x: float = 0
    y: float = 0


class Node(BaseModel):
    id: str
    type: str
    position: Position = Field(default_factory=Position)
    data: dict[str, Any] = Field(default_factory=dict)


class Edge(BaseModel):
    id: str
    source: str
    target: str
    sourceHandle: Optional[str] = None
    targetHandle: Optional[str] = None


class Workflow(BaseModel):
    id: str
    name: str = "Untitled workflow"
    nodes: list[Node] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)
    updated_at: Optional[str] = None
    org_id: Optional[str] = None  # placement in an organization (RBAC-shared) when set


class RunRequest(BaseModel):
    workflow: Workflow
    trigger: dict[str, Any] = Field(default_factory=dict)
