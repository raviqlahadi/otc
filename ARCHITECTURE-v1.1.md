# ANOA v1.1 — Architecture & Code Flow

## System Overview

```
WhatsApp Cloud API
       │
       ▼
┌─────────────────┐     ┌──────────────┐
│  server/webhook │────▶│  Redis       │  (session state, survey state, dedup)
└────────┬────────┘     └──────────────┘
         │
         ▼
┌─────────────────┐     ┌──────────────┐
│  server/flow    │────▶│  PostgreSQL  │  (mastery, interactions, profiles)
└────────┬────────┘     └──────────────┘
         │
    ┌────┴─────────────────────┐
    │          Routes to:       │
    ▼          ▼          ▼    ▼
 Survey    Engine    Feedback  Analytics
Conductor  (BKT)    Generator  Module
```

---

## Module Responsibilities

| Module | File(s) | Role |
|--------|---------|------|
| **Webhook** | `server/webhook.py` | HTTP endpoints, signature validation, dedup, dispatching |
| **Flow Controller** | `server/flow.py` | State machine orchestration — routes messages based on `FlowPhase` |
| **Session Manager** | `session/manager.py` | Redis + PG session state CRUD, phase transitions |
| **Survey Conductor** | `survey/conductor.py` | Manages survey item delivery, validation, state advancement |
| **Affective Scorer** | `survey/scorer.py` | Computes AMAS/interest totals → level classification → DB persist |
| **BKT Config Loader** | `engine/bkt_config.py` | Loads per-KC parameters from JSON resource |
| **Option Tracing Engine** | `engine/option_tracing.py` | BKT mastery update, misconception tracking, KC traversal |
| **Feedback Generator** | `feedback/generator.py` | Retrieves misconception-specific feedback from DB |
| **Feedback Personaliser** | `feedback/personaliser.py` | Selects affective opening, assembles full message, logs event |
| **Verification Selector** | `feedback/verification.py` | Picks verification questions targeting same misconception |
| **Analytics** | `analytics/module.py` | CSV exports for research (trajectories, mastery, affective data) |
| **Messaging** | `messaging/gateway.py`, `messaging/whatsapp_adapter.py` | Platform abstraction, WhatsApp API send/receive |
| **Models** | `models.py` | All dataclasses and enums |
| **Config** | `config.py` | Environment variable loading |

---

## Complete Message Flow (v1.1)

### Startup (`main.py`)

```
1. Connect Redis + PostgreSQL
2. BKTConfigLoader.load_from_json() → per-KC BKTParams dict
3. Instantiate: WhatsAppAdapter → Gateway → Engine → SessionManager
4. Instantiate: SurveyConductor → AffectiveScorer → FeedbackPersonaliser
5. configure() injects all deps into webhook module
6. Start FastAPI on :8000
```

### Incoming Message

```
POST /webhook
  │
  ├─ Validate HMAC signature (WhatsAppAdapter)
  ├─ Normalize payload → NormalizedMessage
  ├─ Dedup check (Redis, 1h TTL)
  │
  ▼
process_message(text, student_id, ...)
  │
  ├─ Load session from Redis (or PG fallback)
  │
  ├─ If session is None (NEW STUDENT):
  │     └─ transition_to_survey() → DEMOGRAPHIC_SURVEY
  │        └─ survey_conductor.start_survey("demographic")
  │           └─ Return first demographic item prompt
  │
  ├─ If DEMOGRAPHIC_SURVEY:
  │     └─ _handle_survey("demographic")
  │        ├─ survey_conductor.process_response()
  │        │   ├─ validate_survey_response()
  │        │   ├─ Store response, advance index
  │        │   └─ Return next prompt (or None if section complete)
  │        │
  │        └─ If section complete:
  │              └─ transition_to_affective_survey()
  │                 └─ survey_conductor.start_survey("affective")
  │                    └─ Return first AMAS item prompt
  │
  ├─ If AFFECTIVE_SURVEY:
  │     └─ _handle_survey("affective")
  │        ├─ process_response() → advance through AMAS + interest items
  │        │
  │        └─ If section complete:
  │              ├─ scorer.score_and_persist() → compute totals, classify, upsert DB
  │              ├─ engine.get_next_kc() → first KC
  │              └─ transition_to_assessment(first_kc)
  │                 └─ Return "assessment begins" message
  │
  ├─ If QUESTION or RETRY:
  │     ├─ validate_answer(text) → must be A/B/C/D
  │     ├─ Load question (by ID or KC)
  │     │
  │     ├─ If CORRECT:
  │     │     ├─ engine.get_next_kc()
  │     │     ├─ If no more KCs → COMPLETED
  │     │     └─ Else → load next question, advance session
  │     │
  │     └─ If WRONG:
  │           ├─ Record misconception in selected_options
  │           ├─ session_mgr.increment_attempt()
  │           │   └─ If attempt_count >= 3 → FEEDBACK
  │           │   └─ Else → RETRY (show remaining attempts)
  │           │
  │           └─ If FEEDBACK triggered:
  │                 └─ _handle_feedback()
  │
  ├─ If FEEDBACK:
  │     └─ _handle_feedback()
  │        ├─ engine.classify_misconception_pattern() → (dominant_id, pattern)
  │        ├─ feedback_gen.get_feedback() → FeedbackContent
  │        ├─ FeedbackGenerator.format_feedback_message() → plain text body
  │        ├─ personaliser.personalise() → prepend affective opening
  │        │   ├─ scorer.get_profile(student_id) → AffectiveProfile (or None)
  │        │   ├─ If profile missing → fallback (MEDIUM, MEDIUM)
  │        │   ├─ select_opening(anxiety, interest, kc_id)
  │        │   ├─ full_message = opening + "\n\n" + body
  │        │   └─ Log to feedback_personalisation table
  │        │
  │        ├─ verification.select_verification_question()
  │        │   └─ If found → VERIFICATION phase
  │        │   └─ If missing → needs_review, move to next KC
  │        └─ Return personalised feedback + verification question
  │
  ├─ If VERIFICATION:
  │     ├─ Check answer (1 attempt only)
  │     ├─ correct → status=mastered
  │     ├─ incorrect → status=needs_review
  │     └─ Move to next KC or COMPLETED
  │
  └─ If COMPLETED:
        └─ Return completion message
```

---

## Data Flow: Affective Scoring

```
Survey Responses (Redis)
       │
       ▼
┌─────────────────────┐
│ compute_totals()    │  Sum AMAS_01..09 and INT_01..03
├─────────────────────┤
│ compute_anxiety_level() │  9-20→LOW, 21-32→MEDIUM, 33-45→HIGH
│ compute_interest_level()│  3-7→LOW, 8-11→MEDIUM, 12-15→HIGH
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│ affective_survey    │  PostgreSQL table (JSONB responses, totals, levels)
└─────────┬───────────┘
          │
          ▼  (at feedback time)
┌─────────────────────┐
│ select_opening()    │  Lookup: (anxiety, interest, kc_id) → opening text
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│ full_message =      │  opening + "\n\n" + feedback_body
│ personalise()       │
└─────────────────────┘
```

---

## Data Flow: BKT Mastery Update

```
resources/09_model_parameters_REVISED_affective_context.json
       │
       ▼  (startup)
┌─────────────────────┐
│ BKTConfigLoader     │  → dict[kc_id, BKTParams]
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│ OptionTracingEngine │  Uses per-KC params for:
│   .process_answer() │    - posterior mastery update
│   .compute_mastery_ │    - P(L₀) initialization
│     update()        │    - Does NOT use affective data
└─────────────────────┘
```

---

## State Machine (FlowPhase)

```
[NEW STUDENT]
      │
      ▼
DEMOGRAPHIC_SURVEY ──(all items answered)──▶ AFFECTIVE_SURVEY
      │                                            │
      │  (session expired, resume)                 │ (all items answered + scored)
      │                                            ▼
      └──────────────────────────────────────▶ QUESTION
                                                   │
                                          correct ─┤─ wrong (attempt < 3)
                                             │     │        │
                                             ▼     │        ▼
                                         QUESTION  │     RETRY
                                        (next KC)  │        │
                                             │     │  wrong (attempt = 3)
                                             │     │        │
                                             │     │        ▼
                                             │     └───▶ FEEDBACK
                                             │              │
                                             │     (verification Q found)
                                             │              │
                                             │              ▼
                                             │        VERIFICATION
                                             │              │
                                             │     correct/incorrect
                                             │              │
                                             ▼              ▼
                                          COMPLETED ◀── (no more KCs)
```

---

## Session Storage (Redis)

| Key Pattern | Data | TTL |
|-------------|------|-----|
| `session:{student_id}` | Hash: flow_phase, current_kc_id, question_id, attempt_count, selected_options | 24h |
| `survey:{student_id}` | JSON: current_item_index, responses, section | 24h |
| `msg:{message_id}` | "1" (dedup flag) | 1h |

---

## Database Tables (PostgreSQL)

### v1.0 Tables
- `knowledge_components` — 3 KCs with prerequisite ordering
- `misconceptions` — 9 misconceptions mapped to KCs
- `questions` — 18 questions (diagnostic + verification)
- `distractor_mappings` — option → misconception mapping
- `students` — phone_hash, timestamps
- `student_mastery` — per-student per-KC mastery state
- `student_misconception_probs` — empirical misconception frequencies
- `interactions` — answer log
- `verification_results` — verification answer log
- `student_progress` — cross-session resumption

### v1.1 Tables (Migration 002)
- `student_profile` — age, program, semester, gender
- `affective_survey` — AMAS/interest JSONB, totals, levels, completion
- `feedback_personalisation` — audit log of affective openings used

---

## Key Design Decisions

1. **Affective context is tone-only** — anxiety/interest levels affect the opening sentence of feedback but never influence BKT mastery calculations.

2. **Fallback rule** — If survey is incomplete, defaults to MEDIUM/MEDIUM so the system never blocks on missing data.

3. **Per-KC params** — Each KC has calibrated BKT parameters (different P(L₀), P(transition)) instead of global defaults. Loaded once at startup.

4. **Survey skip** — Optional demographic/SES items can be skipped. Required AMAS/interest items enforce valid responses.

5. **Backward compatibility** — All new flow controller parameters are optional. If `survey_conductor=None`, the system behaves exactly like v1.0.
