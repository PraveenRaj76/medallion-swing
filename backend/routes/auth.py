"""POST /api/auth/register, POST /api/auth/login.

Thin wrappers over database_engine.register_user() / verify_user() — same
salted-hash, constant-time-compare credential store the Streamlit app
already uses, just exposed as JSON. No session/token issuance yet: this
returns a user_id the frontend holds onto (matches the single-user,
MEDALLION_DEFAULT_USER_ID pattern the other routes already use). Real
session cookies/JWT are a follow-up once the React app has more than one
concurrent caller to distinguish.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from db import database_engine as db
from models.schemas import LoginRequest, RegisterRequest

router = APIRouter()


@router.post("/auth/register")
def post_register(body: RegisterRequest):
    ok, message, user_id = db.register_user(body.username, body.password)
    if not ok:
        raise HTTPException(status_code=400, detail=message)
    return {"ok": True, "message": message, "user_id": user_id}


@router.post("/auth/login")
def post_login(body: LoginRequest):
    ok, message, user_id = db.verify_user(body.username, body.password)
    if not ok:
        raise HTTPException(status_code=401, detail=message)
    return {"ok": True, "message": message, "user_id": user_id}
