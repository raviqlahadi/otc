"""
FastAPI Dependency Injection container.

All dependencies are accessed via app.state (set during lifespan).
This avoids globals and makes testing trivial (override dependencies).
"""

from fastapi import Depends, Request


# --- Infrastructure ---

def get_db_pool(request: Request):
    return request.app.state.db_pool


def get_redis(request: Request):
    return request.app.state.redis


# --- Repositories ---

def get_mastery_repo(request: Request):
    return request.app.state.mastery_repo


def get_question_repo(request: Request):
    return request.app.state.question_repo


def get_interaction_repo(request: Request):
    return request.app.state.interaction_repo


def get_progress_repo(request: Request):
    return request.app.state.progress_repo


# --- Services ---

def get_engine(request: Request):
    return request.app.state.engine


def get_session_mgr(request: Request):
    return request.app.state.session_mgr


def get_gateway(request: Request):
    return request.app.state.gateway


def get_flow_controller(request: Request):
    return request.app.state.flow_controller
