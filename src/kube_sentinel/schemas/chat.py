from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AgentToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)


class AgentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["assistant"] = "assistant"
    content: str = Field(..., min_length=1)
    tool_calls: list[AgentToolCall] = Field(default_factory=list)
