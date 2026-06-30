# ANOA v1.1 — Running & Smoke Test Guide

## Prerequisites

- Docker & Docker Compose
- (Optional) Python 3.11+ for running tests/smoke test outside container

---

## 1. Quick Start (Docker)

```bash
# Clone and enter project
cd manda-research

# Copy env (optional — defaults work for local dev)
cp .env.example .env

# Start everything
docker compose up --build
```

This starts:
- **App** on `http://localhost:8000`
- **PostgreSQL 16** on `localhost:5432` (auto-runs migrations from `migrations/`)
- **Redis 7** on `localhost:6379`

Migrations `001_initial_schema.sql` and `002_affective_context.sql` run automatically on first start.

---

## 2. Seed Data

After containers are running, seed KCs/questions/misconceptions:

```bash
docker compose exec db psql -U postgres -d option_tracing <<'SQL'
INSERT INTO knowledge_components (id, name, description, prerequisite_kc_id, display_order) VALUES
  ('KC_WN_SUB_ZERO', 'Pengurangan Bilangan Cacah Melewati Nol', 'Subtraction with borrowing across zeros', NULL, 1),
  ('KC_INT_NEG_SUB', 'Pengurangan Bilangan Bulat Negatif', 'Integer subtraction with negatives', 'KC_WN_SUB_ZERO', 2),
  ('KC_FRAC_DIV', 'Pembagian Pecahan', 'Fraction division', 'KC_INT_NEG_SUB', 3);

INSERT INTO misconceptions (id, kc_id, name, description, why_incorrect, correct_method) VALUES
  ('M_WN_SMALLER_FROM_LARGER', 'KC_WN_SUB_ZERO', 'Mengurangi angka kecil dari besar', 'Mengurangkan digit kecil dari digit besar pada tiap kolom', 'Posisi nilai tempat harus dijaga', 'Gunakan peminjaman'),
  ('M_WN_BORROW_ZERO', 'KC_WN_SUB_ZERO', 'Gagal meminjam melewati nol', 'Peminjaman melewati angka nol belum lengkap', 'Peminjaman harus diteruskan', 'Lacak peminjaman dari kiri'),
  ('M_WN_PLACE_VALUE', 'KC_WN_SUB_ZERO', 'Kesalahan nilai tempat', 'Digit tertukar atau tidak sejajar', 'Digit harus sejajar', 'Tulis bersusun dan sejajarkan'),
  ('M_INT_DOUBLE_NEG_IGNORED', 'KC_INT_NEG_SUB', 'Tanda negatif ganda diabaikan', 'Mengurangkan negatif dibaca sebagai menambah negatif', 'a-(-b)=a+b', 'Ubah dua minus menjadi plus'),
  ('M_INT_SIGN_LOSS', 'KC_INT_NEG_SUB', 'Tanda salah', 'Besar benar tapi tanda akhir terbalik', 'Tanda menunjukkan posisi', 'Periksa posisi pada garis bilangan'),
  ('M_INT_ABS_VALUE_ADDITION', 'KC_INT_NEG_SUB', 'Menjumlahkan nilai mutlak', 'Menghapus tanda negatif lalu menjumlahkan', 'Tanda tidak boleh dihilangkan', 'Ubah ke penjumlahan lalu tentukan posisi'),
  ('M_FRAC_MULTIPLY_STRAIGHT', 'KC_FRAC_DIV', 'Mengalikan langsung', 'Langsung mengalikan tanpa membalik', 'Ini pembagian bukan perkalian', 'Balik pecahan kedua'),
  ('M_FRAC_NO_INVERT', 'KC_FRAC_DIV', 'Tidak membalik pembagi', 'Pecahan pembagi tidak dibalik', 'Pembagi harus dibalik', 'Pertahankan pertama, balik kedua'),
  ('M_FRAC_INVERT_FIRST', 'KC_FRAC_DIV', 'Membalik pecahan pertama', 'Yang dibalik pecahan pertama bukan kedua', 'Yang dibalik c/d bukan a/b', 'Tulis ulang dengan benar');

INSERT INTO questions (id, kc_id, question_text, correct_option, option_a, option_b, option_c, option_d) VALUES
  ('Q_WN_01', 'KC_WN_SUB_ZERO', '2008 - 1326 = ...', 'A', '682', '1326', '722', '1682');

INSERT INTO distractor_mappings (question_id, option_letter, misconception_id) VALUES
  ('Q_WN_01', 'B', 'M_WN_SMALLER_FROM_LARGER'),
  ('Q_WN_01', 'C', 'M_WN_BORROW_ZERO'),
  ('Q_WN_01', 'D', 'M_WN_PLACE_VALUE');
SQL
```

---

## 3. Run Tests

```bash
# Inside container
docker compose exec app pytest

# Or locally (no DB/Redis needed — tests use mocks)
pip install -e ".[dev]"
pytest
```

Expected: **35 tests pass**.

---

## 4. Smoke Test

### 4.1 Webhook Verification

```bash
curl "http://localhost:8000/webhook?hub.mode=subscribe&hub.verify_token=my_verify_token&hub.challenge=test123"
```

Expected: `test123`

### 4.2 Full Flow Smoke Test

Run the smoke test script against the Docker services:

```bash
# Install deps locally (one-time)
pip install -e ".[dev]"

# Run smoke test (connects to Docker's PG + Redis on localhost)
python3 smoke_test.py
```

```python
# smoke_test.py
import asyncio
import asyncpg
import redis.asyncio as aioredis

from engine.bkt_config import BKTConfigLoader
from engine.option_tracing import OptionTracingEngine
from feedback.generator import FeedbackGenerator
from feedback.personaliser import FeedbackPersonaliser
from feedback.verification import VerificationSelector
from server.flow import process_message
from session.manager import SessionManager
from survey.conductor import SurveyConductor
from survey.scorer import AffectiveScorer


async def main():
    redis_client = aioredis.from_url("redis://localhost:6379/0", decode_responses=False)
    db_pool = await asyncpg.create_pool("postgresql://postgres:postgres@localhost:5432/option_tracing")

    bkt_params = BKTConfigLoader.load_from_json()
    engine = OptionTracingEngine(db_pool, bkt_params)
    session_mgr = SessionManager(redis_client, db_pool)
    feedback_gen = FeedbackGenerator(db_pool)
    verification = VerificationSelector(db_pool)
    survey_conductor = SurveyConductor(redis_client)
    scorer = AffectiveScorer(db_pool)
    personaliser = FeedbackPersonaliser(db_pool, scorer)

    student_id = "smoke_test_student_001"

    async def get_question(id_or_kc):
        from models import Question
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, kc_id, question_text, correct_option, option_a, option_b, option_c, option_d "
                "FROM questions WHERE id=$1 OR kc_id=$1 LIMIT 1", id_or_kc)
            if not row:
                return None
            q = Question(id=row["id"], kc_id=row["kc_id"], question_text=row["question_text"],
                         correct_option=row["correct_option"], option_a=row["option_a"],
                         option_b=row["option_b"], option_c=row["option_c"], option_d=row["option_d"])
            dms = await conn.fetch("SELECT option_letter, misconception_id FROM distractor_mappings WHERE question_id=$1", q.id)
            q.distractor_map = {r["option_letter"]: r["misconception_id"] for r in dms}
            return q

    # Register student
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO students (id, phone_hash) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            student_id, "smoke_test_hash_001")

    print("=" * 60)
    print("SMOKE TEST — ANOA v1.1")
    print("=" * 60)

    # Step 1: First message → starts demographic survey
    resp = await process_message("hi", student_id, session_mgr, engine, feedback_gen, verification,
                                 get_question, survey_conductor, scorer, personaliser)
    print(f"\n[1] Student: hi\n    Bot: {resp[:100]}...")
    assert "mengenal" in resp.lower() or "usia" in resp.lower()

    # Step 2: Answer age
    resp = await process_message("20", student_id, session_mgr, engine, feedback_gen, verification,
                                 get_question, survey_conductor, scorer, personaliser)
    print(f"\n[2] Student: 20\n    Bot: {resp[:100]}...")

    # Step 3: Skip remaining demographics
    for _ in range(12):
        resp = await process_message("lewat", student_id, session_mgr, engine, feedback_gen, verification,
                                     get_question, survey_conductor, scorer, personaliser)
    print(f"\n[3] After skipping demographics:\n    Bot: {resp[:100]}...")

    # Step 4: AMAS items (9x score 3 = medium anxiety)
    for _ in range(9):
        resp = await process_message("3", student_id, session_mgr, engine, feedback_gen, verification,
                                     get_question, survey_conductor, scorer, personaliser)
    print(f"\n[4] After AMAS:\n    Bot: {resp[:100]}...")

    # Step 5: Interest items (3x score 4 = high interest)
    for _ in range(3):
        resp = await process_message("4", student_id, session_mgr, engine, feedback_gen, verification,
                                     get_question, survey_conductor, scorer, personaliser)
    print(f"\n[5] After interest → assessment:\n    Bot: {resp[:150]}...")
    assert "assessment" in resp.lower() or "soal" in resp.lower()

    print("\n" + "=" * 60)
    print("✅ SMOKE TEST PASSED")
    print("=" * 60)

    await db_pool.close()
    await redis_client.close()

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 5. Verify Affective Data

```bash
docker compose exec db psql -U postgres -d option_tracing \
  -c "SELECT student_id, amas_total, interest_total, anxiety_level, interest_level FROM affective_survey;"
```

Expected: `amas_total=27`, `interest_total=12`, `anxiety_level=medium`, `interest_level=high`.

---

## 6. Useful Commands

```bash
# Stop everything
docker compose down

# Reset database (wipe data, re-run migrations)
docker compose down -v && docker compose up --build

# View app logs
docker compose logs -f app

# Shell into app container
docker compose exec app bash

# Shell into database
docker compose exec db psql -U postgres -d option_tracing

# Run a single test
docker compose exec app pytest tests/test_bkt.py -v
```

---

## 7. Environment Variables

Set in `.env` or pass directly:

| Variable | Default | Notes |
|----------|---------|-------|
| `WHATSAPP_PHONE_NUMBER_ID` | `123456` | Dummy for local |
| `WHATSAPP_ACCESS_TOKEN` | `test_token` | Dummy for local |
| `WHATSAPP_VERIFY_TOKEN` | `my_verify_token` | Used in webhook verify |
| `WHATSAPP_APP_SECRET` | `test_secret` | Used for HMAC |
| `DATABASE_URL` | (set by compose) | Auto-configured |
| `REDIS_URL` | (set by compose) | Auto-configured |

---

## 8. Production Deployment

- [ ] Set real WhatsApp credentials in `.env`
- [ ] Use a strong `WHATSAPP_VERIFY_TOKEN`
- [ ] Seed all 18 questions from `resources/06_question_bank.csv`
- [ ] Register webhook URL: `https://yourdomain.com/webhook`
- [ ] Add volume for PostgreSQL data persistence (already in compose)
- [ ] Consider adding `restart: unless-stopped` to services

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `FileNotFoundError: BKT config not found` | Ensure `resources/` is mounted (check docker-compose volumes) |
| `relation "affective_survey" does not exist` | Reset: `docker compose down -v && docker compose up --build` |
| App exits immediately | Check `docker compose logs app` — likely DB not ready (healthcheck should handle this) |
| Smoke test can't connect | Ensure ports 5432/6379 are exposed and containers are running |
| Survey never completes | Verify `resources/11_student_profile_affective_survey_id.csv` has 25 rows |
