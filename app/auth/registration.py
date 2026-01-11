from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.settings.database import SessionLocal
from app.auth.models import User
from app.auth.security import hash_password, verify_password, create_access_token

# USER REGISTRATION
async def user_registration(payload):
    db: Session = SessionLocal()

    existing_user = db.query(User).filter(User.email == payload.email).first()
    if existing_user:
        db.close()
        raise HTTPException(status_code=400, detail="User already exists")

    user = User(
        email=payload.email,
        password=hash_password(payload.password),
        role="user"  # default role
    )

    db.add(user)
    db.commit()
    db.close()

    return "User registered successfully"

# ADMIN ROLE UPDATE
async def update_user_role(payload):
    db: Session = SessionLocal()

    user = db.query(User).filter(User.email == payload.email).first()
    if not user:
        db.close()
        raise HTTPException(status_code=404, detail="User not found")

    user.role = payload.role
    db.commit()
    db.close()

    return f"Role updated to '{payload.role}'"

# VERIFY USER AND GENERATE TOKEN
async def verify_user_and_generate_token(email, password):
    db = SessionLocal()
    user = db.query(User).filter(User.email == email).first()

    if not user or not verify_password(password, user.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token({"sub": user.email})
    return token