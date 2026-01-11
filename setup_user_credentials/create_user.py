from app.settings.database import SessionLocal
from app.auth.models import User
from app.auth.security import hash_password
import os
db = SessionLocal()

users = [
    User(email="admin@example.com", password=hash_password("admin123"), role="admin"),
    User(email="manager@example.com", password=hash_password("manager123"), role="manager"),
    User(email="agent@example.com", password=hash_password("agent123"), role="agent"),
    User(email="user@example.com", password=hash_password("user123"), role="user"),
]

db.add_all(users)
db.commit()
db.close()

print("Users created")

