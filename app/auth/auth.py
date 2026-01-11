from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.settings.database import SessionLocal
from app.auth.models import User
from app.auth.security import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    payload = decode_token(token)
    email = payload.get("sub")

    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=401)
    return user

def require_role(role: str):
    def checker(user=Depends(get_current_user)):
        if user.role != role:
            raise HTTPException(status_code=403)
        return user
    return checker
