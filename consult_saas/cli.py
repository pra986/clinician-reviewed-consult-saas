import argparse
import base64
import hashlib
import hmac
import json
import time

from consult_saas.engine import ClinicianReviewedConsultEngine


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")


def build_demo_jwt(secret: str, clinician_id: str = "clinician_demo_01") -> str:
    header = _b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode("utf-8"))
    payload = _b64url_encode(
        json.dumps(
            {
                "sub": clinician_id,
                "email": f"{clinician_id}@clinic.example.org",
                "subscription_active": True,
                "plan_tier": "pro",
                "exp": int(time.time()) + 3600,
            }
        ).encode("utf-8")
    )
    signing_input = f"{header}.{payload}".encode("utf-8")
    sig = _b64url_encode(hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest())
    return f"{header}.{payload}.{sig}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Clinician-Reviewed Consult SaaS CLI Demo")
    parser.add_argument(
        "--note",
        default="Patient reports persistent dry cough for 5 days. Prescribed Lisinopril 10 mg daily; vitals stable.",
        help="Source clinical encounter note.",
    )
    parser.add_argument("--sign-off", action="store_true", help="Sign off and export the draft.")
    args = parser.parse_args()

    secret = "demo-clerk-secret"
    token = build_demo_jwt(secret)
    engine = ClinicianReviewedConsultEngine(jwt_secret=secret)

    draft = engine.generate_consult_draft(token, args.note)
    print("Generated Draft:", json.dumps(draft.model_dump(mode="json"), indent=2))

    if args.sign_off:
        signed_draft = engine.sign_off(token, draft)
        exported = engine.export_draft(token, signed_draft)
        print("Exported Consultation:", json.dumps(exported, indent=2))
    else:
        print("Export blocked until clinician sign-off is completed (pass --sign-off to export).")


if __name__ == "__main__":
    main()
