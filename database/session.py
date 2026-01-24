from sqlmodel import SQLModel, create_engine, Session
import os
from dotenv import load_dotenv

load_dotenv()

# Render provides DATABASE_URL, Supabase provides it too.
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    # Fallback/Dev config - ensure you have a .env file or set this env var
    # For local dev without supabase key, we might default to sqlite, but
    # the plan is strict Supabase. We will warn.
    print("WARNING: DATABASE_URL not set. Database operations will fail.")
    DATABASE_URL = "sqlite:///./test.db" # Fallback for local testing if env missing

# check_same_thread=False is needed only for SQLite
connect_args = {"check_same_thread": False} if "sqlite" in DATABASE_URL else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

def get_session():
    with Session(engine) as session:
        yield session
