import base64
import hashlib
import hmac
import json
import re
import time
import uuid
from typing import Callable, Dict, List, Optional

from consult_saas.models import ClinicianSession, ConsultationDraft, SignOffReceipt


class AuthError(Exception):
    def __init__(self, message: str, status_code: int = 401) -> None:
        super().__init__(message)
        self.status_code = status_code


class ValidationError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


DOSAGE_PATTERN = re.compile(r"\b\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|units?)\b", re.IGNORECASE)
MEDICATION_PATTERN = re.compile(
    r"\b([A-Za-z][a-z]+(?:in|ol|pril|statin|mycin|cillin|formin|prazole|sartan|ide|one|pam))\b"
)


def _b64url_decode(segment: str) -> bytes:
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + padding)


class ClinicianReviewedConsultEngine:
    def __init__(
        self,
        jwt_secret: Optional[str] = None,
        max_note_chars: int = 10000,
        draft_generator: Optional[Callable[[str], Dict[str, str]]] = None,
    ) -> None:
        self.jwt_secret = jwt_secret
        self.max_note_chars = max_note_chars
        self.draft_generator = draft_generator or self._default_generator

    def verify_clerk_session(self, token: Optional[str]) -> ClinicianSession:
        if not token or not isinstance(token, str) or not token.strip():
            raise AuthError("Missing Clerk JWT token.", status_code=401)

        parts = token.strip().split(".")
        if len(parts) != 3:
            raise AuthError("Malformed Clerk JWT token.", status_code=401)

        header_b64, payload_b64, sig_b64 = parts
        if self.jwt_secret:
            signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
            expected = hmac.new(
                self.jwt_secret.encode("utf-8"), signing_input, hashlib.sha256
            ).digest()
            try:
                actual = _b64url_decode(sig_b64)
            except Exception as exc:
                raise AuthError("Invalid JWT signature encoding.", status_code=401) from exc
            if not hmac.compare_digest(expected, actual):
                raise AuthError("Invalid Clerk JWT signature.", status_code=401)

        try:
            payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
        except Exception as exc:
            raise AuthError("Invalid Clerk JWT payload.", status_code=401) from exc

        exp = payload.get("exp")
        if not isinstance(exp, (int, float)) or int(exp) <= int(time.time()):
            raise AuthError("Clerk JWT token has expired.", status_code=401)

        clinician_id = payload.get("sub") or payload.get("clinician_id")
        if not clinician_id:
            raise AuthError("Clerk JWT missing clinician subject.", status_code=401)

        subscription_active = bool(payload.get("subscription_active", False))
        if not subscription_active:
            raise AuthError("Active clinician subscription required.", status_code=403)

        return ClinicianSession(
            clinician_id=str(clinician_id),
            email=payload.get("email"),
            subscription_active=True,
            plan_tier=str(payload.get("plan_tier", "pro")),
            token_expires_at=int(exp),
        )

    def validate_source_note(self, source_note: Optional[str]) -> str:
        if not source_note or not source_note.strip():
            raise ValidationError("Consultation source note cannot be empty.", status_code=400)
        cleaned = source_note.strip()
        if len(cleaned) > self.max_note_chars:
            raise ValidationError(
                f"Consultation note exceeds maximum length of {self.max_note_chars} characters.",
                status_code=400,
            )
        return cleaned

    def check_source_alignment(self, source_note: str, generated_text: str) -> List[str]:
        source_lower = source_note.lower()
        ungrounded: List[str] = []

        for match in DOSAGE_PATTERN.findall(generated_text):
            normalized = " ".join(match.lower().split())
            if normalized not in " ".join(source_lower.split()):
                if match not in ungrounded:
                    ungrounded.append(match)

        for med in MEDICATION_PATTERN.findall(generated_text):
            if med.lower() not in source_lower and med not in ungrounded:
                ungrounded.append(med)

        return ungrounded

    def _default_generator(self, source_note: str) -> Dict[str, str]:
        snippet = source_note.strip().splitlines()[0][:240]
        return {
            "summary": f"Clinical summary based on source note: {snippet}",
            "assessment": "Clinician review required to confirm differential assessment.",
            "plan": "Follow documented management plan pending clinician sign-off.",
        }

    def generate_consult_draft(self, token: Optional[str], source_note: Optional[str]) -> ConsultationDraft:
        session = self.verify_clerk_session(token)
        cleaned_note = self.validate_source_note(source_note)
        generated = self.draft_generator(cleaned_note)

        summary = generated.get("summary", "").strip()
        assessment = generated.get("assessment", "").strip()
        plan = generated.get("plan", "").strip()

        combined = f"{summary}\n{assessment}\n{plan}"
        ungrounded = self.check_source_alignment(cleaned_note, combined)

        return ConsultationDraft(
            draft_id=f"draft_{uuid.uuid4().hex[:12]}",
            clinician_id=session.clinician_id,
            source_note=cleaned_note,
            summary=summary,
            assessment=assessment,
            plan=plan,
            ungrounded_entities=ungrounded,
            requires_clinician_review=True,
            signed_off=False,
            signoff_receipt=None,
        )

    def sign_off(self, token: Optional[str], draft: ConsultationDraft) -> ConsultationDraft:
        session = self.verify_clerk_session(token)
        if draft.clinician_id != session.clinician_id:
            raise AuthError("Clinician does not own this consultation draft.", status_code=403)

        receipt = SignOffReceipt(
            receipt_id=f"rcpt_{uuid.uuid4().hex[:12]}",
            draft_id=draft.draft_id,
            clinician_id=session.clinician_id,
        )
        return draft.model_copy(
            update={
                "requires_clinician_review": False,
                "signed_off": True,
                "signoff_receipt": receipt,
            }
        )

    def export_draft(self, token: Optional[str], draft: ConsultationDraft) -> Dict[str, object]:
        session = self.verify_clerk_session(token)
        if draft.clinician_id != session.clinician_id:
            raise AuthError("Clinician does not own this consultation draft.", status_code=403)
        if not draft.signed_off or draft.signoff_receipt is None:
            raise ValidationError(
                "Clinician sign-off is mandatory before exporting consultation draft.",
                status_code=400,
            )

        return {
            "draft_id": draft.draft_id,
            "clinician_id": draft.clinician_id,
            "summary": draft.summary,
            "assessment": draft.assessment,
            "plan": draft.plan,
            "ungrounded_entities": draft.ungrounded_entities,
            "signoff_receipt": draft.signoff_receipt.model_dump(mode="json"),
        }
