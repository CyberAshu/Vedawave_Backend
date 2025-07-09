from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
import asyncio

# SQLite database URL
SQLITE_DATABASE_URL = "sqlite:///./chatapp.db"
ASYNC_SQLITE_DATABASE_URL = "sqlite+aiosqlite:///./chatapp.db"

# Create synchronous engine
engine = create_engine(
    SQLITE_DATABASE_URL, 
    connect_args={"check_same_thread": False}
)

# Create async engine
async_engine = create_async_engine(
    ASYNC_SQLITE_DATABASE_URL,
    echo=False
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create async session factory
AsyncSessionLocal = sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Create base class for models
Base = declarative_base()

# Dependency to get database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Async dependency to get database session
async def get_async_db():
    async with AsyncSessionLocal() as session:
        yield session

# Initialize database
async def init_db():
    # Import all models to ensure they are registered
    from models import User, Chat, Message, Attachment
    
    # Create all tables
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    print("Database initialized successfully!")

# Create tables synchronously (for non-async contexts)
def create_tables():
    from models import User, Chat, Message, Attachment
    Base.metadata.create_all(bind=engine)
    print("Database tables created!")

if __name__ == "__main__":
    create_tables()
