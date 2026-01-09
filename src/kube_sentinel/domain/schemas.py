import operator
from enum import Enum
from typing import Annotated, Any, TypedDict

from pydantic import BaseModel, Field


class Diagnosis(BaseModel):
    """
    The agent's understanding of the problem
    """

    root_cause: str = Field(..., description="Technical cause.")
    affected_resource: str = Field(
        ..., description="Name of the deployment/pod"
    )
    evidence: str = Field(
        ..., description="The log line or event that proves this conclusion."
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence level (0.0 - 1.0)."
    )


class PathRiskLevel(str, Enum):
    """Risk level of applying a remediation."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RemediationPlan(BaseModel):
    """
    The proposed solution from the Agent.
    It must include a valid Kubernetes JSON Merge Patch.
    """

    description: str = Field(..., description="Human-readable summary")

    resource_name: str = Field(
        ..., description="Name of the deployment to patch."
    )
    namespace: str = Field(..., description="Namespace of the resource.")

    # The Agent must construct the specific JSON to fix the issue
    patch_json: dict[str, Any] = Field(
        ...,
        description="The exact JSON Merge Patch to apply (e.g. {'spec': ...}).",
    )

    risk_level: PathRiskLevel = Field(
        ..., description="low, medium, high or critical"
    )


class SreAgentState(TypedDict):
    """
    The Working Memory of the Agent.
    """

    # Chat History (accumulates tool outputs and agent reasoning)
    messages: Annotated[list[Any], operator.add]

    # Context
    namespace: str

    # The Plan (Populated when the Agent decides to solve)
    remediation_plan: RemediationPlan | None

    # Validation Flags
    dry_run_passed: bool
    user_approval: bool
