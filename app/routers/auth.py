from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from app.config import APP_ENV, SESSION_MAX_AGE_SECONDS
from app.services.auth import SESSION_COOKIE, create_session_token, password_matches


router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    password: str


@router.post("/login", status_code=204)
async def login(payload: LoginRequest, response: Response) -> None:
    if not password_matches(payload.password):
        raise HTTPException(status_code=401, detail="Incorrect password")
    response.set_cookie(
        SESSION_COOKIE,
        create_session_token(SESSION_MAX_AGE_SECONDS),
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=APP_ENV == "production",
        samesite="lax",
    )


@router.post("/logout", status_code=204)
async def logout(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE)
