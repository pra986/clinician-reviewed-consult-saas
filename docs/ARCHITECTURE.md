# Architecture Overview

## 1. Request & Authentication Flow
- **Client (Next.js + Clerk):** Authenticates the clinician and sends a Bearer JWT in the `Authorization` header.
- **API Layer (FastAPI on AWS Lambda Web Adapter):** Runs FastAPI behind AWS Lambda Web Adapter for serverless scaling.
- **Server-Side JWT & Subscription Gate:** Every request is verified server-side for a valid, non-expired Clerk JWT and an active subscription status before processing clinical notes.

## 2. Clinical Note Validation & Drafting
- **Input Bounds:** Rejects empty notes and notes exceeding `MAX_CONSULT_NOTE_CHARS` (default 12,000 characters).
- **Draft Generation:** Produces a structured `ConsultationDraft` (summary, assessment, plan, and extracted clinical entities).

## 3. Source-Note Clinical Entity Alignment
- Extracts medication names and dosages (e.g., `mg`, `mcg`, `g`, `mL`, `units`) from both the source clinical note and the generated draft.
- Any dosage or medication present in the draft that is not grounded in the source note is flagged as a hallucination/unverified entity (`ungrounded_entities`) and blocks silent acceptance.

## 4. Mandatory Clinician Sign-Off Gate
- Drafts cannot be exported until a clinician explicitly signs off, producing an immutable `SignOffReceipt` with clinician ID, timestamp, and draft ID.
- Export requests without a valid `SignOffReceipt` are rejected.
