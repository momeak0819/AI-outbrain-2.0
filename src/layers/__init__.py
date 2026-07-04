"""Five-layer content ingestion architecture."""

from .knowledge import KnowledgeDecision, create_knowledge_result
from .models import (
    AcquisitionResult,
    DeliveryResult,
    KnowledgeContext,
    KnowledgeResult,
    ProcessingResult,
    SourceDocument,
    SourceInput,
    WorkflowEnvelope,
)

__all__ = [
    "SourceInput",
    "SourceDocument",
    "AcquisitionResult",
    "ProcessingResult",
    "KnowledgeContext",
    "KnowledgeResult",
    "KnowledgeDecision",
    "create_knowledge_result",
    "DeliveryResult",
    "WorkflowEnvelope",
]
