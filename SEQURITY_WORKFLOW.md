# 🛡️ OWASP-Compliant FastAPI API (SQLite + JWT + RBAC)

A **secure, production-ready FastAPI backend** implementing **OWASP API Security Top-10 best practices**, featuring:

- 🔐 JWT Authentication
- 👥 Role-Based Access Control (RBAC)
- 🚦 Rate Limiting
- 🗄️ SQLite Database (file-based)
- 📊 Logging & Security Headers
- ⚡ FastAPI + SQLAlchemy

Designed for **MVPs, internal tools, and scalable foundations** (500–50K+ users).

---

## 📌 Key Features

- OWASP API Security Top-10 aligned
- Multiple roles per endpoint
- SQLite database stored inside project
- Secure password hashing (bcrypt)
- Rate limiting with SlowAPI
- Swagger UI authentication
- Easy migration to PostgreSQL

---

## 🧱 Tech Stack

| Component | Technology |
|---------|------------|
| API Framework | FastAPI |
| ORM | SQLAlchemy |
| Authentication | JWT (OAuth2 Bearer) |
| Database | SQLite |
| Rate Limiting | SlowAPI |
| Password Hashing | bcrypt |
| API Docs | Swagger / OpenAPI |


---

## 🚀 Getting Started

### 1️⃣ Create virtual environment

```bash
python -m venv .venv
.venv\Scripts\activate   # Windows
```

### 2️⃣ Install dependencies
```bash
pip install -r requirements.txt
```

### 3️⃣ Initialize database
```bash
python setup_user_credentials/init_db.py
```
This creates the SQLite database:
```bash
app.db
```

### 4️⃣ Create sample users

```bash
python setup_user_credentials/create_user.py
```

### Default users:
| Email                                             | Password   | Role    |
|---------------------------------------------------|------------|---------|
| [admin@example.com](mailto:admin@example.com)     | admin123   | admin   |
| [manager@example.com](mailto:manager@example.com) | manager123 | manager |
| [agent@example.com](mailto:agent@example.com)     | agent123   | agent   |
| [user@example.com](mailto:user@example.com)       | user123    | user    |


### 5️⃣ Run the server
```bash
uvicorn app:app --reload --port 8000
```
### Open Swagger UI:
```bash
http://localhost:8000/docs
```
---
### 🔐 Authentication Flow
#### 🔹 Login

#### POST /login
```bash
{
  "email": "admin@example.com",
  "password": "admin123"
}
```

#### Response:
```bash
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer"
}
```
#### 🔹 Use Access Token

#### Add HTTP header:
```bash
Authorization: Bearer <access_token>
```

#### This is required for protected endpoints.

#### 👥 Role-Based Access Control (RBAC)
#### Supported Roles
```bash
admin
manager
agent
user
```

#### Example Protected Endpoint
```
@app.post("/api/search")
async def search_properties(
    user=Depends(require_roles("admin", "manager", "agent"))
):
    ...
```
#### Access Matrix

| Endpoint      | admin | manager | agent | user |
| ------------- | ----- | ------- | ----- | ---- |
| `/admin`      | ✅     | ❌       | ❌     | ❌    |
| `/api/search` | ✅     | ✅       | ✅     | ❌    |
| `/profile`    | ✅     | ✅       | ✅     | ✅    |




#### Rate Limiting

#### Example:

```bash
@limiter.limit("30/minute")
```

## 🔐 Protection Coverage

### Protects Against:
- Brute-force login
- API abuse
- DoS attempts  
  *(OWASP API4 – Unrestricted Resource Consumption)*

---

## 🛡️ Security Headers

### Automatically Applied:
- **X-Frame-Options:** `DENY`
- **X-Content-Type-Options:** `nosniff`
- **Strict-Transport-Security`**

*(OWASP API8 – Security Misconfiguration)*

---

## 🧠 OWASP API Security Coverage

| OWASP Risk | Status |
|-----------|--------|
| API1 – Broken Object Level Authorization | ✅ |
| API2 – Broken Authentication | ✅ |
| API3 – Mass Assignment | ✅ |
| API4 – Unrestricted Resource Consumption | ✅ |
| API5 – Broken Function Level Authorization | ✅ |
| API8 – Security Misconfiguration | ✅ |
| API9 – Improper Inventory Management | ✅ |

---

## 📈 Scalability Notes

### SQLite is Suitable For:
- 500 – 50,000 users
- MVPs and internal systems
- Moderate API traffic

### Migrate to PostgreSQL When:
- Multiple application servers are required
- High concurrent writes are expected
- Enterprise-scale workloads are needed

> Migration is seamless using **SQLAlchemy**.

---

## 🔧 Production Recommendations

- Change `SECRET_KEY` in `security.py`
- Store secrets in `.env`
- Use HTTPS (Nginx / API Gateway)
- Enable structured logging
- Add monitoring (Prometheus / ELK)
