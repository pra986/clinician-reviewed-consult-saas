import base64
import hashlib
import hmac
import json
import time

import pytest

from consult_saas.engine import AuthError, ClinicianReviewedConsultEngine, ValidationError


SECRET = "test-clerk-jwt-secret"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")


def make_jwt(
    sub: str = "clinician_123",
    subscription_active: bool = True,
    exp_offset: int = 3600,
) -> str:
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode("utf-8"))
    payload = _b64url(
        json.dumps(
            {
                "sub": sub,
                "email": f"{sub}@clinic.example.org",
                "subscription_active": subscription_active,
                "plan_tier": "pro",
                "exp": int(time.time()) + exp_offset,
            }
        ).encode("utf-8")
    )
    signing_input = f"{header}.{payload}".encode("utf-8")
    sig = _b64url(hmac.new(SECRET.encode("utf-8"), signing_input, hashlib.sha256).digest())
    return f"{header}.{payload}.{sig}"


def test_missing_or_expired_jwt_rejected_401() -> None:
    engine = ClinicianReviewedConsultEngine(jwt_secret=SECRET)

    with pytest.raises(AuthError) as missing_exc:
        engine.generate_consult_draft(None, "Patient has mild headache.")
    assert missing_exc.value.status_code == 401

    expired_token = make_jwt(exp_offset=-60)
    with pytest.raises(AuthError) as expired_exc:
        engine.generate_consult_draft(expired_token, "Patient has mild headache.")
    assert expired_exc.value.status_code == 401


def test_empty_and_oversized_note_rejected() -> None:
    engine = ClinicianReviewedConsultEngine(jwt_secret=SECRET, max_note_chars=100)
    token = make_jwt()

    with pytest.raises(ValidationError):
        engine.generate_consult_draft(token, "   ")

    with pytest.raises(ValidationError):
        engine.generate_consult_draft(token, "A" * 101)


def test_invented_dosage_flagged_by_source_alignment() -> None:
    def hallucinating_generator(_note: str) -> dict[str, str]:
        return {
            "summary": "Patient prescribed Lisinopril 10 mg.",
            "assessment": "Hypertension managed.",
            "plan": "Increase to 40 mg daily and start Amoxicillin 500 mg.",
        }

    engine = ClinicianReviewedConsultEngine(
        jwt_secret=SECRET,
        draft_generator=hallucinating_generator,
    )
    token = make_jwt()
    source_note = "Patient reports stable BP on Lisinopril 10 mg daily."

    draft = engine.generate_consult_draft(token, source_note)
    assert "40 mg" in draft.ungrounded_entities
    assert "500 mg" in draft.ungrounded_entities
    assert "Amoxicillin" in draft.ungrounded_entities


def test_export_blocked_without_clinician_signoff() -> None:
    engine = ClinicianReviewedConsultEngine(jwt_secret=SECRET)
    token = make_jwt()
    draft = engine.generate_consult_draft(token, "Patient has seasonal allergic rhinitis.")

    with pytest.raises(ValidationError):
        engine.export_draft(token, draft)

    signed_draft = engine.sign_off(token, draft)
    assert signed_draft.signed_off is True
    assert signed_draft.signoff_receipt is not None

    exported = engine.export_draft(token, signed_draft)
    assert exported["draft_id"] == draft.draft_id
    assert exported["signoff_receipt"]["clinician_id"] == "clinician_123"
