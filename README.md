# Option Tracing Chatbot

WhatsApp-based adaptive math assessment chatbot using Option Tracing — a BKT extension that maps wrong answers to specific misconceptions.

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

# Run database migration
psql $DATABASE_URL -f migrations/001_initial_schema.sql
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

## Tests

```bash
pytest
```
