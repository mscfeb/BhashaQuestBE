
from datetime import datetime, timedelta, timezone
from uuid import UUID
from fastapi import Request
import jwt
from fastapi import APIRouter, Depends, HTTPException, Response, status
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.entities import User

router = APIRouter(prefix="/api/auth", tags=["authentication"])

SESSION_COOKIE_NAME = "bhasha_session"
SESSION_DURATION = timedelta(days=7)


class GoogleLoginRequest(BaseModel):
    credential: str = Field(min_length=1, max_length=10000)


def create_session_token(user_id: UUID) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + SESSION_DURATION,
        "type": "session",
    }
    return jwt.encode(
        payload,
        settings.session_secret,
        algorithm="HS256",
    )


@router.post("/google")
def google_login(
    body: GoogleLoginRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    # Verify the Google-signed ID token, including its audience.
    try:
        claims = id_token.verify_oauth2_token(
            body.credential,
            GoogleRequest(),
            settings.google_client_id,
        )
    except (ValueError, Exception):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google sign-in verification failed",
        )

    # Accept only Google-issued identities with a verified email.
    if claims.get("iss") not in (
        "accounts.google.com",
        "https://accounts.google.com",
    ):
        raise HTTPException(status_code=401, detail="Invalid identity issuer")

    if not claims.get("sub") or not claims.get("email_verified"):
        raise HTTPException(
            status_code=401,
            detail="A verified Google account is required",
        )

    google_sub = claims["sub"]
    email = claims.get("email")
    display_name = claims.get("name")

    if not email:
        raise HTTPException(status_code=401, detail="Google email is missing")

    user = db.scalar(
        select(User).where(User.google_sub == google_sub)
    )

    if user is None:
        user = User(
            google_sub=google_sub,
            email=email,
            display_name=display_name,
        )
        db.add(user)

        try:
            db.commit()
            db.refresh(user)
        except IntegrityError:
            # Another request may have created this Google user concurrently.
            db.rollback()
            user = db.scalar(
                select(User).where(User.google_sub == google_sub)
            )
            if user is None:
                raise HTTPException(
                    status_code=500,
                    detail="Could not create user",
                )
    else:
        # Refresh profile details from the verified identity.
        user.email = email
        user.display_name = display_name
        db.commit()
        db.refresh(user)

    session_token = create_session_token(user.id)

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_token,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        max_age=int(SESSION_DURATION.total_seconds()),
        path="/",
    )

    return {
        "user": {
            "id": str(user.id),
            "email": user.email,
            "displayName": user.display_name,
        }
    }


@router.post("/logout", status_code=204)
def logout(response: Response):
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
    )
    return response



def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    token = request.cookies.get(SESSION_COOKIE_NAME)

    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        claims = jwt.decode(
            token,
            settings.session_secret,
            algorithms=["HS256"],
        )
        if claims.get("type") != "session":
            raise jwt.InvalidTokenError("Invalid session type")
        user_id = UUID(claims["sub"])
    except (jwt.InvalidTokenError, ValueError, KeyError):
        raise HTTPException(
            status_code=401,
            detail="Session expired or invalid",
        )

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")

    return user


@router.get("/me")
def get_me(user: User = Depends(get_current_user)):
    return {
        "id": str(user.id),
        "email": user.email,
        "displayName": user.display_name,
    }
