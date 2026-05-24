"""Auth router — login and session management."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

class LoginRequest(BaseModel):
    username: str
    password: str

@router.post("/api/auth/login")
async def login(body: LoginRequest):
    """
    Phase 1: simple username/password check against SQLite users table.
    Returns a session token stored in cookie.
    TODO: replace with bcrypt + JWT in production.
    """
    from app.database import get_db, User
    import bcrypt, secrets
    db = next(get_db())
    try:
        user = db.query(User).filter(User.username == body.username, User.is_active == 1).first()
        if not user:
            raise HTTPException(401, "Invalid credentials")
        if not bcrypt.checkpw(body.password.encode(), user.password_hash.encode()):
            raise HTTPException(401, "Invalid credentials")
        token = secrets.token_urlsafe(32)
        # TODO: store token in sessions table with expiry
        return {"token": token, "username": user.username, "role": user.role}
    finally:
        db.close()

@router.post("/api/auth/logout")
async def logout():
    return {"status": "ok"}
