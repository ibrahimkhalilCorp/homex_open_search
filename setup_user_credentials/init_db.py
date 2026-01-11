from app.settings.database import engine, Base
from app.auth.models import User

Base.metadata.create_all(bind=engine)
print("Database & tables created")
