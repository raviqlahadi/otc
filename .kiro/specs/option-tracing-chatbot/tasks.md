# Implementation Plan: Option Tracing Chatbot

## Overview

This plan implements a WhatsApp-based adaptive math assessment chatbot using Option Tracing — a Knowledge Tracing variant extending BKT with misconception probabilities. The implementation uses FastAPI, Redis (session state), PostgreSQL (persistence), and a messaging gateway abstraction. Tasks are ordered to build foundation layers first (data models, core engine) then wire up the API and integration layers.

## Tasks

- [ ] 1. Set up project structure and core data models
  - [ ] 1.1 Initialize project structure with FastAPI, dependencies, and configuration
    - Create directory layout: `messaging/`, `server/`, `session/`, `engine/`, `feedback/`, `analytics/`, `validation/`, `tests/`
    - Create `pyproject.toml` or `requirements.txt` with: fastapi, uvicorn, redis[hiredis], asyncpg, httpx, hypothesis, pytest, pytest-asyncio
    - Create configuration module (`config.py`) loading env vars for: WhatsApp credentials, Redis URL, PostgreSQL DSN, BKT parameters
    - _Requirements: 8.1, 11.4_

  - [ ] 1.2 Create PostgreSQL schema and migration scripts
    - Write SQL migration file with all tables: `knowledge_components`, `misconceptions`, `questions`, `distractor_mappings`, `students`, `student_mastery`, `student_misconception_probs`, `interactions`, `verification_results`, `student_progress`
    - Include all CHECK constraints, FOREIGN KEY references, and indexes as specified in the design
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

  - [ ] 1.3 Create Python data models and enums
    - Implement dataclasses/models: `Platform`, `NormalizedMessage`, `OutgoingMessage`, `FlowPhase`, `SessionState`, `BKTParams`, `StudentMastery`, `AnswerResult`, `FeedbackContent`
    - Implement `Question` model with `distractor_map: dict[str, str]` mapping option letter to misconception ID
    - _Requirements: 2.1, 7.1, 6.1_

- [ ] 2. Implement input validation and messaging abstraction
  - [ ] 2.1 Implement InputValidator
    - Create `validation/input_validator.py` with `validate_answer(text: str) -> tuple[bool, str | None]`
    - Strip whitespace, normalize to uppercase, accept only {A, B, C, D}
    - Return `(True, normalized_option)` for valid input, `(False, None)` for invalid
    - _Requirements: 1.3, 1.4_

  - [ ]* 2.2 Write property tests for input validation
    - **Property 2: Valid input acceptance** — For any single character from {A, B, C, D} with arbitrary whitespace and case, validator accepts and returns normalized uppercase
    - **Property 3: Invalid input preserves attempt count** — For any non-A/B/C/D string, validator rejects (returns False, None)
    - **Validates: Requirements 1.3, 1.4, 3.2**

  - [ ] 2.3 Implement Messaging Gateway and abstract adapter interface
    - Create `messaging/gateway.py` with `MessagingAdapter` ABC and `MessagingGateway` class
    - Implement `normalize()`, `send()`, `validate_webhook()` interface methods
    - _Requirements: 11.1, 11.2, 11.3, 11.4_

  - [ ] 2.4 Implement WhatsApp Adapter
    - Create `messaging/whatsapp_adapter.py` implementing `MessagingAdapter`
    - Implement payload normalization extracting sender, text, message_id from WhatsApp Cloud API webhook structure
    - Implement `send()` posting to WhatsApp Cloud API via httpx
    - Implement `validate_webhook()` checking X-Hub-Signature-256 HMAC-SHA256
    - _Requirements: 8.2, 8.3, 11.2_

  - [ ]* 2.5 Write property tests for messaging normalization and webhook validation
    - **Property 18: Webhook signature validation** — Valid HMAC accepted, invalid/missing rejected
    - **Property 20: Message normalization** — Valid payloads produce NormalizedMessage with non-empty sender_id, text, and correct platform
    - **Validates: Requirements 8.2, 11.2**

- [ ] 3. Implement Session Manager
  - [ ] 3.1 Implement SessionManager with Redis and PostgreSQL
    - Create `session/manager.py` with `SessionManager` class
    - Implement `get_session()`: load from Redis, fall back to PostgreSQL for resumption
    - Implement `save_session()`: persist to Redis with 86400s TTL
    - Implement `persist_progress()`: save to PostgreSQL for cross-session continuity
    - Implement `increment_attempt()`: increment count, transition to FEEDBACK at attempt 3, RETRY otherwise
    - Implement `_serialize()` / `_deserialize()` for Redis hash format
    - _Requirements: 7.1, 7.2, 7.3, 3.2, 3.4_

  - [ ]* 3.2 Write property tests for session state
    - **Property 17: Session state serialization round-trip** — Any valid SessionState survives serialize → deserialize unchanged
    - **Property 9: Attempt counting and feedback trigger** — attempt_count increments by 1 per wrong answer; at 3, phase → FEEDBACK
    - **Property 10: Session context preservation during retry** — During retry, question_id preserved, selected_options accumulated, attempt_count updated
    - **Validates: Requirements 7.1, 3.1, 3.2, 3.3, 3.4**

- [ ] 4. Implement Option Tracing Engine
  - [ ] 4.1 Implement BKT mastery computation
    - Create `engine/option_tracing.py` with `OptionTracingEngine` class
    - Implement `_update_mastery()`: BKT posterior update with P(L₀), P(guess), P(slip), P(transit)
    - Ensure probability values clamped to [0.0, 1.0]
    - Implement `initialize_student()`: set P(mastery)=P(L₀), P(transition)=initial rate, P(misconception)=0.0 for all KCs
    - _Requirements: 6.1, 6.2, 6.6_

  - [ ]* 4.2 Write property tests for BKT computation
    - **Property 14: BKT probability bounds invariant** — For any sequence of interactions, P(mastery), P(transition), P(misconception) remain in [0.0, 1.0]
    - **Property 16: New student initialization** — P(mastery)=P(L₀), P(transition)=initial rate, P(misconception)=0.0 for all KCs
    - **Validates: Requirements 6.1, 6.2, 6.3, 6.6, 12.1**

  - [ ] 4.3 Implement option-to-misconception identification and interaction logging
    - Implement `process_answer()`: check correctness, look up distractor mapping for misconception_id, log interaction
    - Implement `_log_interaction()`: write to `interactions` table with all required fields
    - Implement `_update_misconception_prob()`: compute empirical frequency from misconception history
    - _Requirements: 2.2, 2.3, 6.3_

  - [ ]* 4.4 Write property tests for option tracing
    - **Property 5: Distractor-misconception mapping integrity** — Each distractor maps to exactly one misconception; correct option not in mapping
    - **Property 6: Option-to-misconception identification** — Wrong option returns matching misconception_id from stored mapping
    - **Property 7: Interaction logging completeness** — Log entry contains all fields: selected_option, misconception_id, attempt_number, student_id, question_id, timestamp
    - **Validates: Requirements 2.1, 2.2, 2.3**

  - [ ] 4.5 Implement misconception pattern classification
    - Implement `classify_misconception_pattern()`: classify as "consistent" if any misconception selected ≥2 times, else "varied"
    - Implement tie-breaking: when equal frequency, use most recent attempt's misconception as dominant
    - _Requirements: 2.4, 2.5_

  - [ ]* 4.6 Write property test for misconception classification
    - **Property 8: Misconception pattern classification** — "consistent" when same misconception ≥2 times, "varied" otherwise; tie-break by recency
    - **Validates: Requirements 2.4, 2.5, 4.4**

  - [ ] 4.7 Implement KC graph traversal
    - Implement `get_next_kc()`: determine next unmastered KC respecting prerequisite relationships from `knowledge_components` table
    - Return `None` when all KCs are completed
    - _Requirements: 6.5_

  - [ ]* 4.8 Write property test for KC graph traversal
    - **Property 15: KC graph traversal respects prerequisites** — Next KC only selected if all its prerequisites are completed/mastered
    - **Validates: Requirements 6.5**

- [ ] 5. Checkpoint - Core engine validation
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 6. Implement Feedback Generator and Verification Logic
  - [ ] 6.1 Implement FeedbackGenerator
    - Create `feedback/generator.py` with `FeedbackGenerator` class
    - Implement `get_feedback()`: query misconception feedback from DB, fall back to generic if not found
    - Implement `format_feedback_message()`: plain-text with (a) misconception name/description, (b) why incorrect, (c) correct method
    - _Requirements: 4.1, 4.2, 4.3, 4.5_

  - [ ]* 6.2 Write property test for feedback structure
    - **Property 11: Feedback message structure** — Non-generic feedback contains all 3 components in order: misconception name/description, why incorrect, correct method
    - **Validates: Requirements 4.2**

  - [ ] 6.3 Implement verification question selection and phase logic
    - Implement verification question selection: different question, same KC, targets same misconception
    - Implement verification state transitions: correct → "mastered", incorrect → "needs_review"
    - Handle missing verification question: log event, skip verification, set "needs_review"
    - Allow exactly 1 attempt for verification
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [ ]* 6.4 Write property tests for verification phase
    - **Property 12: Verification question selection constraints** — Selected question is different, same KC, distractors map to same misconception
    - **Property 13: Verification phase state transitions** — Correct → "mastered", incorrect → "needs_review", exactly 1 attempt consumed
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5**

- [ ] 7. Implement Question Formatting and Conversation Flow
  - [ ] 7.1 Implement question formatting for delivery
    - Create utility to format question as plain text: stem on first line, then "A. ...\nB. ...\nC. ...\nD. ..." each on separate lines
    - _Requirements: 1.2_

  - [ ]* 7.2 Write property test for question formatting
    - **Property 1: Question formatting structure** — Formatted output contains stem + exactly 4 labeled options (A, B, C, D) on separate lines
    - **Validates: Requirements 1.2**

  - [ ] 7.3 Implement core conversation flow orchestrator
    - Create `server/flow.py` with `process_message()` function that orchestrates the state machine
    - Handle all phases: QUESTION (deliver question), RETRY (re-present on wrong), FEEDBACK (deliver feedback + verification), VERIFICATION (process verification answer), COMPLETED (completion message)
    - Handle correct answer advancing to next KC or completing assessment
    - Handle invalid input re-prompting without state change
    - Wire together: InputValidator → SessionManager → OptionTracingEngine → FeedbackGenerator
    - _Requirements: 1.1, 1.4, 1.5, 1.6, 3.1, 3.3, 4.1, 5.1_

  - [ ]* 7.4 Write property test for correct answer advancement
    - **Property 4: Correct answer advances to next KC** — Submitting correct option transitions to next KC or COMPLETED
    - **Validates: Requirements 1.5, 1.6**

- [ ] 8. Implement Webhook Server and Deduplication
  - [ ] 8.1 Implement FastAPI webhook endpoints
    - Create `server/webhook.py` with FastAPI app
    - Implement GET `/webhook` for WhatsApp verification challenge
    - Implement POST `/webhook`: validate signature → normalize → deduplicate → process → respond
    - Implement deduplication using Redis with 1-hour TTL for processed message IDs
    - Implement error handling: Redis unavailable → graceful error message, invalid signature → 403
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 7.4_

  - [ ]* 8.2 Write property test for message deduplication
    - **Property 19: Message deduplication (idempotency)** — Same message_id submitted twice results in no additional processing, still returns HTTP 200
    - **Validates: Requirements 8.5**

- [ ] 9. Implement Student Registration and Progress Resumption
  - [ ] 9.1 Implement student identification and registration
    - Implement new student registration: hash phone number, initialize mastery using P(L₀) values
    - Implement returning student detection: load existing mastery and resume from correct KC
    - Store phone numbers as SHA-256 hashes in `phone_hash` column
    - _Requirements: 12.1, 12.2, 12.3_

  - [ ]* 9.2 Write property tests for student registration
    - **Property 24: Phone number stored as hash** — Stored phone_hash ≠ raw phone number, is deterministic hash
    - **Property 23: Student progress resumption round-trip** — Persisted progress loads correctly with right current KC and completed KCs
    - **Validates: Requirements 12.1, 12.2, 12.3, 7.3**

- [ ] 10. Checkpoint - Full flow integration
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 11. Implement Analytics Module and Data Export
  - [ ] 11.1 Implement Analytics Module with CSV export
    - Create `analytics/module.py` with `AnalyticsModule` class
    - Implement `export_learning_trajectories()`: per-student interactions ordered by timestamp, CSV format
    - Implement `export_misconception_frequencies()`: population-level per-KC misconception counts, CSV format
    - Implement `export_diagnostic_outputs()`: P(mastery), P(transition), P(misconception) for all students, CSV format
    - Implement `_anonymize_student_id()`: SHA-256 hash truncated to 16 chars
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

  - [ ]* 11.2 Write property tests for analytics export
    - **Property 21: Export records ordered by timestamp** — Per-student trajectories are strictly ascending by timestamp
    - **Property 22: Export anonymization** — No raw phone numbers appear in any export; all IDs are one-way hashes
    - **Validates: Requirements 10.1, 10.5**

- [ ] 12. Wire application together and final integration
  - [ ] 12.1 Create application dependency injection and startup
    - Create `server/dependencies.py` with FastAPI dependency injection for: Redis client, PostgreSQL pool, MessagingGateway, SessionManager, OptionTracingEngine, FeedbackGenerator, AnalyticsModule
    - Create `main.py` application entry point with lifespan management (connect/disconnect Redis and PostgreSQL)
    - Wire the WhatsApp adapter into the gateway, register webhook routes
    - _Requirements: 8.1, 11.4_

  - [ ]* 12.2 Write integration tests for full conversation flow
    - Test complete flows: question → 3 wrong → feedback → verification → next KC
    - Test session resumption after expiry
    - Test Redis unavailability graceful degradation
    - _Requirements: 1.1, 3.1, 4.1, 5.1, 7.3, 7.4, 8.4_

- [ ] 13. Final checkpoint - All tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document (Properties 1-24)
- Unit tests validate specific examples and edge cases
- The design uses Python with FastAPI — all implementation uses Python 3.11+
- Hypothesis is the PBT library; pytest is the test runner
- BKT parameters are pre-calibrated and loaded from configuration, not computed at runtime

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3"] },
    { "id": 2, "tasks": ["2.1", "2.3"] },
    { "id": 3, "tasks": ["2.2", "2.4", "3.1", "4.1"] },
    { "id": 4, "tasks": ["2.5", "3.2", "4.2", "4.3"] },
    { "id": 5, "tasks": ["4.4", "4.5", "4.7"] },
    { "id": 6, "tasks": ["4.6", "4.8", "6.1", "6.3"] },
    { "id": 7, "tasks": ["6.2", "6.4", "7.1"] },
    { "id": 8, "tasks": ["7.2", "7.3"] },
    { "id": 9, "tasks": ["7.4", "8.1", "9.1"] },
    { "id": 10, "tasks": ["8.2", "9.2", "11.1"] },
    { "id": 11, "tasks": ["11.2", "12.1"] },
    { "id": 12, "tasks": ["12.2"] }
  ]
}
```
