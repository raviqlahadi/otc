import asyncio
from contextlib import asynccontextmanager

import asyncpg
import redis.asyncio as aioredis
import uvicorn

from analytics.module import AnalyticsModule
from config import settings
from engine.option_tracing import OptionTracingEngine
from feedback.generator import FeedbackGenerator
from feedback.verification import VerificationSelector
from messaging.gateway import MessagingGateway
from messaging.whatsapp_adapter import WhatsAppAdapter
from models import BKTParams, Platform
from server.webhook import app, configure
from session.manager import SessionManager
from session.registration import StudentRegistration


@asynccontextmanager
async def lifespan(application):
    # Startup
    redis_client = aioredis.from_url(settings.redis_url, decode_responses=False)
    db_pool = await asyncpg.create_pool(settings.database_url)

    bkt_params = {
        "kc1": BKTParams(settings.bkt_p_l0, settings.bkt_p_guess, settings.bkt_p_slip, settings.bkt_p_transit),
        "kc2": BKTParams(settings.bkt_p_l0, settings.bkt_p_guess, settings.bkt_p_slip, settings.bkt_p_transit),
        "kc3": BKTParams(settings.bkt_p_l0, settings.bkt_p_guess, settings.bkt_p_slip, settings.bkt_p_transit),
    }

    adapter = WhatsAppAdapter(
        settings.whatsapp_phone_number_id,
        settings.whatsapp_access_token,
        settings.whatsapp_verify_token,
        settings.whatsapp_app_secret,
    )
    gateway = MessagingGateway({Platform.WHATSAPP: adapter})
    engine = OptionTracingEngine(db_pool, bkt_params)
    session_mgr = SessionManager(redis_client, db_pool)
    feedback_gen = FeedbackGenerator(db_pool)
    verification = VerificationSelector(db_pool)

    configure(gateway, session_mgr, engine, feedback_gen, verification, redis_client)

    yield

    # Shutdown
    await db_pool.close()
    await redis_client.close()


app.router.lifespan_context = lifespan

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
