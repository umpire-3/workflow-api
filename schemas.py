from enum import Enum
from pydantic import BaseModel


class WorkflowBase(BaseModel):
    name: str


class WorkflowRead(WorkflowBase):
    id: int


class WorkflowCreate(WorkflowBase):
    pass


class WorkflowUpdate(BaseModel):
    name: str | None = None


class NodeBase(BaseModel):
    workflow_id: int


class StartNodeCreate(NodeBase):
    successor_id: int | None = None


class StartNodeUpdate(BaseModel):
    workflow_id: int | None = None
    successor_id: int | None = None


class EndNodeCreate(NodeBase):
    predecessors: list[int] | None = None


class EndNodeUpdate(BaseModel):
    workflow_id: int | None = None
    predecessors: list[int] | None = None


class NodeStatus(str, Enum):
    pending = 'pending'
    sent = 'sent'
    opened = 'opened'


class MessageNodeCreate(NodeBase):
    status: NodeStatus
    text: str
    predecessors: list[int] | None = None
    successor_id: int | None = None


class MessageNodeUpdate(BaseModel):
    workflow_id: int | None = None
    status: NodeStatus | None = None
    text: str | None = None
    predecessors: list[int] | None = None
    successor_id: int | None = None


class ConditionNodeCreate(NodeBase):
    condition: str
    predecessors: list[int] | None = None
    yes_successor_id: int | None = None
    no_successor_id: int | None = None


class ConditionNodeUpdate(BaseModel):
    workflow_id: int | None = None
    condition: str | None = None
    predecessors: list[int] | None = None
    yes_successor_id: int | None = None
    no_successor_id: int | None = None
