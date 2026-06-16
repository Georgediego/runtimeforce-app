
import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Define the path to the database file
DATABASE_DIR = os.path.expanduser("~/.local/share/runtimeforce")
DATABASE_PATH = os.path.join(DATABASE_DIR, "runtime.db")

# Ensure the directory exists
os.makedirs(DATABASE_DIR, exist_ok=True)

# Create the SQLAlchemy engine
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DATABASE_PATH}"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

# Create a SessionLocal class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create a Base class for declarative models
Base = declarative_base()

def create_db_and_tables():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
