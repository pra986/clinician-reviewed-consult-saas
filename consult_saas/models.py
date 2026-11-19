from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional
from pydantic import BaseModel, Field


class ClinicianSession(BaseModel):
    clinician_id: str
    email: Optional[str] = None
    subscription_active: bool = False
    plan_tier: str = "free"
    token_expires_at: int


class ConsultationDraft(BaseModel):
    draft_id: str
    clinician_id: str
    source_note: str
    summary: str
    assessment: str
    plan: str
    ungrounded_entities: List[str] = Field(default_factory=list)
    requires_clinician_review: bool = True
    signed_off: bool = False
    signoff_receipt: Optional["SignOffReceipt"] = None


class SignOffReceipt(BaseModel):
    receipt_id: str
    draft_id: str
    clinician_id: str
    signed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    attestation: str = "Reviewed and approved by licensed clinician."
