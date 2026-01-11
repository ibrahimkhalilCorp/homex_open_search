from pydantic import BaseModel, EmailStr
from typing import Optional
from enum import Enum

class UserRole(str, Enum):
    admin = "admin"
    manager = "manager"
    agent = "agent"
    user = "user"

# ============================================================
# PYDANTIC MODELS
# ============================================================

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class SearchRequest(BaseModel):
    query: Optional[str] = "property with 2+ acres in HI"
    page: Optional[int] = 1
    size: Optional[int] = 20
    use_cache: Optional[bool] = True

class RegistrationRequest(BaseModel):
    email: EmailStr
    password: str

class RoleUpdateRequest(BaseModel):
    email: EmailStr
    role: UserRole