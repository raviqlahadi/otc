from contextlib import asynccontextmanager

import asyncpg
import redis.asyncio as aioredis
import uvicorn

from config import settings
from engine.bkt_config import BKTConfigLoader
from engine.option_tracing import OptionTracingEngine
from feedback.generator import FeedbackGenerator
from feedback.personaliser import FeedbackPersonaliser
from feedback.verification import VerificationSelector
from messaging.gateway import MessagingGateway
from messaging.whatsapp_adapter import WhatsAppAdapter
from models.messaging import Platform
from repositories.interactions import InteractionRepository
from repositories.mastery import MasteryRepository
from repositories.progress import ProgressRepository
from repositories.questions import QuestionRepository
from server.flow import FlowController
from server.webhook import app
from session.manager import SessionManager
from survey.conductor import SurveyConductor
from survey.scorer import AffectiveScorer


@asynccontextmanager
async def lifespan(application):
    # Infrastructure
    redis_client = aioredis.from_url(settings.redis_url, decode_responses=False)
    db_pool = await asyncpg.create_pool(settings.database_url)

    # Repositories
    mastery_repo = MasteryRepository(db_pool)
    question_repo = QuestionRepository(db_pool)
    interaction_repo = InteractionRepository(db_pool)
    progress_repo = ProgressRepository(db_pool)

    # Services
    bkt_params = BKTConfigLoader.load_from_json()
    adapter = WhatsAppAdapter(
        settings.whatsapp_phone_number_id,
        settings.whatsapp_access_token,
        settings.whatsapp_verify_token,
        settings.whatsapp_app_secret,
    )
    gateway = MessagingGateway({Platform.WHATSAPP: adapter})
    engine = OptionTracingEngine(mastery_repo, interaction_repo, progress_repo, bkt_params)
    session_mgr = SessionManager(redis_client, db_pool)
    feedback_gen = FeedbackGenerator(db_pool)
    verification = VerificationSelector(db_pool)
    survey_conductor = SurveyConductor(redis_client)
    scorer = AffectiveScorer(db_pool)
    personaliser = FeedbackPersonaliser(db_pool, scorer)

    # FlowController — single orchestrator
    flow_controller = FlowController(
        session_mgr=session_mgr,
        engine=engine,
        feedback_gen=feedback_gen,
        verification=verification,
        question_repo=question_repo,
        survey_conductor=survey_conductor,
        scorer=scorer,
        personaliser=personaliser,
    )

    # Wire to app.state for DI
    application.state.db_pool = db_pool
    application.state.redis = redis_client
    application.state.mastery_repo = mastery_repo
    application.state.question_repo = question_repo
    application.state.interaction_repo = interaction_repo
    application.state.progress_repo = progress_repo
    application.state.engine = engine
    application.state.session_mgr = session_mgr
    application.state.gateway = gateway
    application.state.flow_controller = flow_controller

    yield

    # Shutdown
    await db_pool.close()
    await redis_client.close()


app.router.lifespan_context = lifespan

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
