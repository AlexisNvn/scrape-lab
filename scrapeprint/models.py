from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Engine(StrEnum):
    chromium = "chromium"
    obscura = "obscura"


class Scenario(StrEnum):
    products = "products"
    testimonials = "testimonials"
    reviews = "reviews"
    product_detail = "product_detail"
    js_links = "js_links"


class Extraction(BaseModel):
    records: list[dict[str, Any]] = Field(default_factory=list)
    expected_count: int | None = None
    complete: bool = False
    evidence: dict[str, Any] = Field(default_factory=dict)


class Validation(BaseModel):
    duplicate_record_count: int = 0
    missing_required_fields: dict[str, int] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not (self.duplicate_record_count or self.missing_required_fields or self.errors)


class RunResult(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    schema_version: int = 1
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    session_id: str
    engine: Engine
    engine_version: str = "unknown"
    scenario: Scenario
    run_number: int = Field(ge=1)
    warmup: bool = False
    success: bool = False
    extracted_record_count: int = Field(default=0, ge=0)
    duplicate_record_count: int = Field(default=0, ge=0)
    missing_required_fields: dict[str, int] = Field(default_factory=dict)
    validation_errors: list[str] = Field(default_factory=list)
    startup_time_s: float = Field(default=0, ge=0)
    navigation_time_s: float = Field(default=0, ge=0)
    extraction_time_s: float = Field(default=0, ge=0)
    total_time_s: float = Field(default=0, ge=0)
    peak_memory_bytes: int = Field(default=0, ge=0)
    cpu_time_s: float = Field(default=0, ge=0)
    error_type: str | None = None
    error_message: str | None = None
    extraction_path: str | None = None
    settings: dict[str, Any] = Field(default_factory=dict)
