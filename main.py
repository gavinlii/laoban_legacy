from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from policy_loader import load_policy
from webgame import SessionStore

BASE_DIR = Path(__file__).resolve().parent
CHECKPOINT_PATH = os.getenv("CHECKPOINT_PATH", str(BASE_DIR / "policy_main.pt"))

policy = load_policy(CHECKPOINT_PATH)
sessions = SessionStore(policy)

app = FastAPI(title="laoban.cards API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class NewGameRequest(BaseModel):
    bot_first: bool = False
    seed: Optional[int] = None


class ActionRequest(BaseModel):
    session_id: str
    action_index: int


class ResetRequest(BaseModel):
    session_id: str
    bot_first: Optional[bool] = None
    seed: Optional[int] = None


@app.get("/")
def root():
    return {
        "ok": True,
        "message": "laoban.cards backend is running",
        "health_endpoint": "/health",
    }


@app.get("/health")
def health():
    return {
        "ok": True,
        "checkpoint": policy.path,
        "encoder": policy.encoder_spec.name,
        "state_dim": policy.encoder_spec.state_dim,
        "action_dim": policy.encoder_spec.action_dim,
        "value_head_kind": policy.value_head_kind,
    }


@app.post("/api/new-game")
def new_game(req: NewGameRequest):
    controller = sessions.create(bot_first=req.bot_first, seed=req.seed)
    return controller.state_payload()


@app.post("/api/action")
def action(req: ActionRequest):
    try:
        controller = sessions.get(req.session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found.")

    try:
        controller.human_play_by_index(req.action_index)
    except (ValueError, IndexError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return controller.state_payload()


@app.post("/api/reset")
def reset(req: ResetRequest):
    try:
        controller = sessions.get(req.session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found.")

    if req.bot_first is not None:
        controller.bot_first = req.bot_first
    if req.seed is not None:
        controller.seed = req.seed
    controller.reset(initial=False)
    return controller.state_payload()


@app.get("/api/state/{session_id}")
def state(session_id: str):
    try:
        controller = sessions.get(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found.")
    return controller.state_payload()