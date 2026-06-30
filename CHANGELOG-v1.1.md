# ANOA v1.1 — Changelog Report

## Summary

Version 1.1 adds **affective context** to the ANOA Option Tracing Chatbot. Students now complete a demographic + affective survey (AMAS anxiety scale + math interest) before assessment begins. Survey results determine the emotional tone of feedback messages. BKT parameters are now loaded per-KC from a JSON resource file instead of global environment variables.

---

## New Features

### 1. Affective Survey Flow
- New flow phases: `DEMOGRAPHIC_SURVEY` → `AFFECTIVE_SURVEY` → assessment
- 25 survey items loaded from `resources/11_student_profile_affective_survey_id.csv`
  - 4 demographic items (age, program, semester, gender)
  - 9 SES context items (optional)
  - 9 AMAS anxiety items (required, Likert 1-5)
  - 3 math interest items (required, Likert 1-5)
- Survey state persisted in Redis with 24h TTL
- Optional items can be skipped with "lewat" / "skip" / "-"
- Invalid responses prompt retry without advancing

### 2. Affective Scoring
- AMAS total (sum of 9 items, range 9-45) → `anxiety_level`:
  - LOW: 9–20
  - MEDIUM: 21–32
  - HIGH: 33–45
- Interest total (sum of 3 items, range 3-15) → `interest_level`:
  - LOW: 3–7
  - MEDIUM: 8–11
  - HIGH: 12–15
- Scores persisted to `affective_survey` table on completion

### 3. Feedback Tone Personalisation
- Feedback messages prefixed with affective opening based on student's anxiety + interest levels
- Openings loaded from `resources/08_feedback_library_REVISED_affective_openings.csv`
- Fallback chain: KC-specific opening → generic opening → hardcoded default ("Mari kita lihat soal ini bersama! 📝")
- All personalisation events logged to `feedback_personalisation` audit table
- **Affective context does NOT affect mastery calculation** — tone only

### 4. Per-KC BKT Parameters
- Parameters loaded from `resources/09_model_parameters_REVISED_affective_context.json`
- Each KC has independent: `p_L0`, `p_guess`, `p_slip`, `p_transition`, `mastery_threshold`, `needs_review_threshold`
- Replaces previous global env-based defaults (all KCs used same values)
- Values validated at load time (all probabilities must be in [0.0, 1.0])

### 5. Fallback Rule
- If survey is incomplete or missing, system defaults to `anxiety_level=medium`, `interest_level=medium`
- Assessment continues normally — feedback still gets personalised with medium-tone opening

### 6. Analytics Extension
- `export_affective_profiles()` — anonymised affective survey data (totals, levels, completion status)
- `export_feedback_personalisation_log()` — audit trail of which openings were used per student/KC
- `export_full_research_dump()` — aggregates all 5 export types into a single dict

---

## Files Created

| File | Purpose |
|------|---------|
| `survey/__init__.py` | Package init |
| `survey/conductor.py` | Survey validation, item loading, SurveyConductor state machine |
| `survey/scorer.py` | AMAS/interest scoring + classification + DB persistence |
| `engine/bkt_config.py` | BKTConfigLoader — loads per-KC params from JSON |
| `feedback/personaliser.py` | FeedbackPersonaliser — tone selection + message assembly |
| `migrations/002_affective_context.sql` | DB schema: student_profile, affective_survey, feedback_personalisation |

## Files Modified

| File | Changes |
|------|---------|
| `models.py` | Added `AffectiveLevel` enum, `AffectiveProfile`, `SurveyItem`, `SurveyState`, `KCConfig` dataclasses; extended `FlowPhase` with `DEMOGRAPHIC_SURVEY`, `AFFECTIVE_SURVEY` |
| `session/manager.py` | Added `transition_to_survey()`, `transition_to_affective_survey()`, `transition_to_assessment()` |
| `server/flow.py` | Integrated survey routing, added `_handle_survey()`, wired personaliser into `_handle_feedback()` |
| `server/webhook.py` | Extended `configure()` to accept survey_conductor/scorer/personaliser; passes them to `process_message()` |
| `main.py` | Replaced env-based BKT params with `BKTConfigLoader.load_from_json()`; instantiates SurveyConductor, AffectiveScorer, FeedbackPersonaliser |
| `analytics/module.py` | Added `export_affective_profiles()`, `export_feedback_personalisation_log()`, `export_full_research_dump()` |

---

## Database Schema Changes (Migration 002)

```sql
-- New tables
student_profile       -- demographics (age 15-65, program, semester, gender)
affective_survey      -- AMAS/interest JSONB responses, totals, levels, completion status
feedback_personalisation  -- audit log of personalised feedback events
```

Key constraints:
- `amas_total` CHECK (9-45), `interest_total` CHECK (3-15)
- `anxiety_level` and `interest_level` CHECK IN ('low', 'medium', 'high')
- Unique `student_id` on both profile and survey tables

---

## Backward Compatibility

- All 35 existing v1.0 tests pass without modification
- `process_message()` new parameters (`survey_conductor`, `scorer`, `personaliser`) are optional — if `None`, system behaves identically to v1.0
- Existing students with sessions in QUESTION/RETRY/FEEDBACK/VERIFICATION phases continue as before
- Only new students (no existing session) enter the survey flow

---

## Configuration Changes

- **Removed dependency on**: `BKT_P_L0`, `BKT_P_GUESS`, `BKT_P_SLIP`, `BKT_P_TRANSIT` env vars for KC params (still in config.py for reference)
- **New dependency**: `resources/09_model_parameters_REVISED_affective_context.json` must exist at startup (raises `FileNotFoundError` otherwise)
- **New resource**: `resources/11_student_profile_affective_survey_id.csv` (survey items)
- **New resource**: `resources/08_feedback_library_REVISED_affective_openings.csv` (feedback openings)
