"""Stable data models for the five product layers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import re
from typing import Any, Callable


LAYER_STAGES = frozenset(
    {"source", "acquisition", "processing", "knowledge", "delivery"}
)
ERROR_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
ACQUISITION_ARTIFACT_KINDS = frozenset({"audio", "video", "file"})
ACQUISITION_ARTIFACT_ROLES = frozenset({"primary", "source", "derived"})
ACQUISITION_ARTIFACT_OWNERSHIPS = frozenset(
    {"user_owned", "acquisition_temp", "persistent"}
)
ACQUISITION_ARTIFACT_CLEANUP_POLICIES = frozenset(
    {"never", "on_processing_complete", "manual"}
)


class SourceType(str, Enum):
    AUTO = "auto"
    DOUYIN = "douyin"
    LOCAL_AUDIO = "local_audio"
    YOUTUBE = "youtube"
    BILIBILI = "bilibili"
    GENERIC_VIDEO = "generic_video"
    X_VIDEO = "x_video"
    VIMEO = "vimeo"
    TWITCH = "twitch"
    TIKTOK = "tiktok"
    INSTAGRAM = "instagram"
    XIAOHONGSHU = "xiaohongshu"


class InputKind(str, Enum):
    UNKNOWN = "unknown"
    URL = "url"
    PATH = "path"
    TEXT = "text"


@dataclass(frozen=True)
class LayerFailure:
    """Canonical, side-effect-free failure contract shared by all five layers."""

    stage: str
    error_code: str
    error: str
    recoverable: bool = False

    def __post_init__(self) -> None:
        if self.stage not in LAYER_STAGES:
            allowed = ", ".join(sorted(LAYER_STAGES))
            raise ValueError(
                f"Invalid failure stage {self.stage!r}; expected one of: {allowed}"
            )
        if not self.error_code or not ERROR_CODE_PATTERN.fullmatch(self.error_code):
            raise ValueError(
                "error_code must be a non-empty snake_case machine code"
            )
        if not self.error:
            raise ValueError("error must be a non-empty user-readable message")
        if not isinstance(self.recoverable, bool):
            raise TypeError("recoverable must be bool")


@dataclass
class SourceInput:
    source_type: str = SourceType.AUTO.value
    url: str = ""
    text: str = ""
    audio_file: str = ""
    raw_input: str = ""
    input_kind: str = InputKind.UNKNOWN.value
    metadata: dict[str, Any] = field(default_factory=dict)

    def normalized(self) -> SourceInput:
        """Return a normalized copy while preserving legacy input precedence."""
        raw_input = self.raw_input
        input_kind = self.input_kind
        normalization_source = "raw_input" if raw_input else "default"

        if self.audio_file:
            raw_input = self.audio_file
            input_kind = InputKind.PATH.value
            normalization_source = "audio_file"
        elif self.url:
            raw_input = self.url
            input_kind = InputKind.URL.value
            normalization_source = "url"
        elif self.text:
            raw_input = self.text
            input_kind = InputKind.TEXT.value
            normalization_source = "text"

        metadata = dict(self.metadata)
        metadata["normalization_source"] = normalization_source
        return SourceInput(
            source_type=self.source_type,
            url=self.url,
            text=self.text,
            audio_file=self.audio_file,
            raw_input=raw_input,
            input_kind=input_kind,
            metadata=metadata,
        )


@dataclass(frozen=True)
class SourceMatch:
    source_type: str
    normalized_input: str
    input_kind: str
    media_type: str
    detected_by: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SourceDocument:
    status: str = "pending"
    source_type: str = ""
    title: str = ""
    author: str = ""
    original_url: str = ""
    media_type: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    error_code: str = ""
    error: str = ""
    recoverable: bool = False


@dataclass(frozen=True)
class AcquisitionArtifact:
    """A typed acquisition output with explicit ownership and cleanup intent."""

    path: str
    kind: str
    role: str
    ownership: str
    cleanup_policy: str
    mime: str = ""

    def __post_init__(self) -> None:
        if not self.path:
            raise ValueError("artifact path must be non-empty")
        if self.kind not in ACQUISITION_ARTIFACT_KINDS:
            raise ValueError(
                f"invalid artifact kind {self.kind!r}; expected one of: "
                f"{', '.join(sorted(ACQUISITION_ARTIFACT_KINDS))}"
            )
        if self.role not in ACQUISITION_ARTIFACT_ROLES:
            raise ValueError(
                f"invalid artifact role {self.role!r}; expected one of: "
                f"{', '.join(sorted(ACQUISITION_ARTIFACT_ROLES))}"
            )
        if self.ownership not in ACQUISITION_ARTIFACT_OWNERSHIPS:
            raise ValueError(
                f"invalid artifact ownership {self.ownership!r}; expected one of: "
                f"{', '.join(sorted(ACQUISITION_ARTIFACT_OWNERSHIPS))}"
            )
        if self.cleanup_policy not in ACQUISITION_ARTIFACT_CLEANUP_POLICIES:
            raise ValueError(
                f"invalid artifact cleanup_policy {self.cleanup_policy!r}; "
                "expected one of: "
                f"{', '.join(sorted(ACQUISITION_ARTIFACT_CLEANUP_POLICIES))}"
            )
        if self.ownership == "user_owned" and self.cleanup_policy != "never":
            raise ValueError(
                "user_owned artifacts must use cleanup_policy='never'"
            )
        if (
            self.ownership == "acquisition_temp"
            and self.cleanup_policy == "never"
        ):
            raise ValueError(
                "acquisition_temp artifacts must use cleanup_policy "
                "'on_processing_complete' or 'manual'"
            )


@dataclass
class AcquisitionResult:
    status: str = "pending"
    media_type: str = ""
    media_path: str = ""
    artifacts: list[str] = field(default_factory=list)
    error_code: str = ""
    error: str = ""
    recoverable: bool = False
    artifact_records: list[AcquisitionArtifact] = field(default_factory=list)


@dataclass
class ProcessingResult:
    status: str = "pending"
    engine: str = ""
    transcript: str = ""
    transcript_chars: int = 0
    normalized: bool = False
    artifacts: list[str] = field(default_factory=list)
    error_code: str = ""
    error: str = ""
    recoverable: bool = False
    processing_mode: str = "asr"
    raw_transcript: str = ""
    normalized_text: str = ""
    segments: list[dict[str, Any]] = field(default_factory=list)
    markdown_path: str = ""
    txt_path: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass
class KnowledgeResult:
    status: str = "pending"
    content_mode: str = "original"
    review_id: str = ""
    review_status: str = ""
    suggested_category: str = ""
    target_path: str = ""
    final_card_path: str = ""
    final_index_path: str = ""
    error_code: str = ""
    error: str = ""
    recoverable: bool = False
    fallback: str = ""
    review_path: str = ""
    draft_path: str = ""
    recommended_next_step: str = ""
    readiness: dict[str, Any] | None = None
    vault_validation: dict[str, Any] | None = None
    mcp_finalization_incomplete: dict[str, Any] | None = None
    vault_write_not_confirmed: dict[str, Any] | None = None


@dataclass
class KnowledgeContext:
    """Injected routing dependencies for the Knowledge layer."""

    content_mode: str = "original"
    interaction_channel: str = "auto"
    route_report: dict[str, Any] | None = None
    route_report_provider: Callable[[], dict[str, Any]] | None = None
    readiness: dict[str, Any] | None = None
    readiness_provider: Callable[[], dict[str, Any]] | None = None
    review_creator: (
        Callable[[dict[str, Any], str, str], dict[str, Any]] | None
    ) = None


@dataclass
class DeliveryResult:
    status: str = "pending"
    channel: str = "auto"
    reply_mode: str = "desktop"
    reply_text: str = ""
    artifacts: list[str] = field(default_factory=list)
    error_code: str = ""
    error: str = ""
    recoverable: bool = False


@dataclass
class WorkflowEnvelope:
    success: bool
    source: SourceDocument = field(default_factory=SourceDocument)
    acquisition: AcquisitionResult = field(default_factory=AcquisitionResult)
    processing: ProcessingResult = field(default_factory=ProcessingResult)
    knowledge: KnowledgeResult = field(default_factory=KnowledgeResult)
    delivery: DeliveryResult = field(default_factory=DeliveryResult)
    next: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
