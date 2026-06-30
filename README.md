# Option Tracing Chatbot

WhatsApp-based adaptive math assessment chatbot using Option Tracing — a BKT extension that maps wrong answers to specific misconceptions.

## Architecture

Clean Architecture with FastAPI dependency injection:

```
models/          → Domain entities (no dependencies)
engine/          → Business logic (BKT math, misconception classification)
repositories/    → Data access layer (PostgreSQL queries)
server/          → HTTP layer (FastAPI routes, DI, flow orchestration)
session/         → Session state management (Redis + PG)
feedback/        → Feedback generation + affective personalisation
survey/          → Multi-step survey conductor + scoring
messaging/       → Platform adapters (WhatsApp, extensible)
validation/      → Input validation utilities
analytics/       → Usage tracking
```

### Dependency Direction

```
webhook.py → FlowController → Engine → Repositories → Models
                             → SessionManager
                             → FeedbackGenerator
                             → SurveyConductor
```

All dependencies point **inward**. Business logic never imports from HTTP or infrastructure layers.

### Key Design Decisions

- **FastAPI `Depends()` + `app.state`** — dependencies wired in `main.py` lifespan, accessed via `server/deps.py`
- **Repository pattern** — SQL lives in `repositories/`, engine has zero DB knowledge
- **FlowController class** — single entry point `handle(text, student_id) → str`, all deps injected via `__init__`
- **Domain models split by concern** — `models/assessment.py`, `models/session.py`, `models/survey.py`, `models/messaging.py`

## Project Structure

```
manda-research/
├── main.py                      # App entrypoint + DI wiring (lifespan)
├── config.py                    # Pydantic settings (.env)
├── models/
│   ├── __init__.py              # Re-exports for backward compat
│   ├── messaging.py             # Platform, NormalizedMessage, OutgoingMessage
│   ├── assessment.py            # BKTParams, Question, StudentMastery, AnswerResult
│   ├── session.py               # FlowPhase, SessionState
│   └── survey.py                # SurveyItem, SurveyState, AffectiveProfile
├── engine/
│   ├── option_tracing.py        # BKT engine (pure logic + repo calls)
│   └── bkt_config.py            # KC parameter loading from JSON
├── repositories/
│   ├── mastery.py               # Student mastery CRUD
│   ├── questions.py             # Question lookup by ID/KC
│   ├── interactions.py          # Answer interaction logging
│   └── progress.py              # KC progress + next-KC ordering
├── server/
│   ├── webhook.py               # FastAPI routes (GET/POST /webhook)
│   ├── flow.py                  # FlowController — state machine orchestrator
│   ├── deps.py                  # Dependency injection (Depends functions)
│   └── formatting.py            # Message formatting helpers
├── session/
│   ├── manager.py               # Redis session + PG resume
│   └── registration.py          # Student registration
├── feedback/
│   ├── generator.py             # Misconception feedback lookup
│   ├── personaliser.py          # Affective-context opening selection
│   └── verification.py          # Verification question selection
├── survey/
│   ├── conductor.py             # Multi-step survey flow
│   └── scorer.py                # Affective profile scoring
├── messaging/
│   ├── gateway.py               # MessagingGateway + MessagingAdapter ABC
│   └── whatsapp_adapter.py      # WhatsApp Cloud API implementation
├── analytics/
│   └── module.py                # Analytics tracking
├── validation/
│   └── input_validator.py       # Input validation (A/B/C/D)
├── migrations/
│   ├── 001_initial_schema.sql
│   └── 002_affective_context.sql
├── resources/                   # CSV/JSON data files
├── tests/                       # pytest test suite
├── pyproject.toml
├── Dockerfile
└── docker-compose.yml
```

## Prerequisites

- Python 3.11+
- PostgreSQL
- Redis

## Setup

```bash
# Install dependencies
pip install -e ".[dev]"

# Configure environment
cp .env.example .env
# Edit .env with your credentials

# Run database migrations
psql $DATABASE_URL -f migrations/001_initial_schema.sql
psql $DATABASE_URL -f migrations/002_affective_context.sql
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `WHATSAPP_PHONE_NUMBER_ID` | WhatsApp Business phone number ID |
| `WHATSAPP_ACCESS_TOKEN` | WhatsApp Cloud API access token |
| `WHATSAPP_VERIFY_TOKEN` | Webhook verification token (you define this) |
| `WHATSAPP_APP_SECRET` | App secret for HMAC signature validation |
| `REDIS_URL` | Redis connection URL |
| `DATABASE_URL` | PostgreSQL connection string |
| `BKT_P_L0` | Initial mastery probability (default: 0.3) |
| `BKT_P_GUESS` | Guess probability (default: 0.25) |
| `BKT_P_SLIP` | Slip probability (default: 0.1) |
| `BKT_P_TRANSIT` | Learning transition rate (default: 0.1) |

## Run

```bash
python main.py
```

The server starts on `http://0.0.0.0:8000`. Register `https://yourdomain.com/webhook` as the WhatsApp webhook URL.

### Docker

```bash
docker-compose up
```

## Tests

```bash
pytest
```

## How It Works

1. **Student sends message** → WhatsApp webhook → `server/webhook.py`
2. **FlowController** checks session state and routes to appropriate handler
3. **Survey phase** — demographic + affective questionnaire via `survey/conductor.py`
4. **Assessment phase** — questions served from `repositories/questions.py`
5. **Answer processing** — BKT update via `engine/option_tracing.py`
6. **After 3 wrong answers** — misconception feedback + affective personalisation
7. **Verification question** — confirms whether misconception is resolved
8. **Next KC** — advances based on mastery threshold + prerequisite order

## Adding New Features

### New messaging platform (e.g. Telegram)
1. Create `messaging/telegram_adapter.py` implementing `MessagingAdapter`
2. Register in `main.py` lifespan: `gateway = MessagingGateway({..., Platform.TELEGRAM: TelegramAdapter()})`

### New repository query
1. Add method to appropriate repo in `repositories/`
2. Call from engine or service layer — never from webhook

### Testing
Mock the repository layer to unit-test business logic without DB:
```python
async def test_bkt_update():
    engine = OptionTracingEngine(mock_mastery_repo, mock_interaction_repo, mock_progress_repo, params)
    result = engine.compute_mastery_update(mastery, correct=True, params=bkt_params)
    assert result.p_mastery > mastery.p_mastery
```
