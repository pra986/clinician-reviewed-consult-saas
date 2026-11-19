# Clinician-Reviewed Consult SaaS (Project 26 / D1: Production Track)

AWS Lambda Web Adapter healthcare consultation SaaS with server-side Clerk JWT validation, source-note entity checks, and mandatory clinician sign-off.

## Architecture

- **Frontend**: Next.js (App Router) with Clerk client authentication and clinician review workspace.
- **Backend**: FastAPI running on AWS Lambda via **AWS Lambda Web Adapter** (`PORT=8000`) behind API Gateway / Lambda Function URL.
- **Auth & Identity**: Server-side Clerk JWT verification (RS256 JWKS validation) enforcing tenant/clinician role claims on every protected route.
- **Safety & Grounding**: Deterministic source-note entity verification ensuring generated summaries/patient letters do not introduce ungrounded medications, dosages, or diagnoses, paired with a mandatory clinician sign-off gate.

## 6-Stage Workflow

1. **Authenticate**: Clinician signs in via Clerk; Next.js attaches Bearer JWT to FastAPI requests.
2. **Ingest Consultation Note**: Structured/unstructured encounter note is validated against the input contract.
3. **Draft Clinical Summary**: LLM generates a structured clinical summary, follow-up plan, and patient-facing letter.
4. **Source-Note Entity Check**: Verifier cross-checks extracted entities (medications, doses, allergies, diagnoses) against the raw source note.
5. **Mandatory Clinician Sign-Off**: Draft remains in `pending_clinician_review` until an authenticated clinician explicitly approves and signs off (`signed_off_by`, `signed_off_at`).
6. **Audit & Export**: Immutable audit record is persisted; approved consultation output is released.

## Data Contract

- **Request (`ConsultRequest`)**: `consult_id`, `patient_ref`, `source_note`, `clinician_id` (derived from verified Clerk JWT `sub`).
- **Response (`ConsultDraftResponse`)**: `consult_id`, `clinical_summary`, `patient_letter`, `entity_check_passed`, `ungrounded_entities`, `status` (`pending_clinician_review` | `approved`), `signed_off_by`, `signed_off_at`.

## Production Controls

- **Server-Side Clerk JWT Validation**: Rejects missing, expired, or invalid-issuer tokens (`401 Unauthorized`).
- **Source-Note Entity Checks**: Flags any entity not grounded in `source_note` before sign-off is permitted.
- **Mandatory Clinician Sign-Off**: Blocks final export/release unless `approved=True` with verified clinician identity.
- **AWS Lambda Web Adapter Readiness**: Stateless FastAPI container with `/health` probe and structured JSON logging.

## Local Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

Run tests:

```bash
pytest -v
```

## Attribution

Inspired by and adapted from `ed-donner/production` (`week1` Healthcare Consultation SaaS production track).
