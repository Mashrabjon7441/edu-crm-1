import os
from sqlalchemy import create_all, create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from models import db

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_URL = f'sqlite:///{os.path.join(BASE_DIR, "database.db")}'

engine = create_engine(DB_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db_session():
    return SessionLocal()
