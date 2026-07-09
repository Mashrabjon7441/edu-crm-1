import os
from sqlalchemy import create_engine, text, inspect

DATABASE_URL = os.getenv("DATABASE_URL", f'sqlite:///crm.db')
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)

def add_columns():
    inspector = inspect(engine)
    
    try:
        teachers_cols = [col['name'] for col in inspector.get_columns('teachers')]
        with engine.begin() as conn:
            if 'experience' not in teachers_cols:
                conn.execute(text("ALTER TABLE teachers ADD COLUMN experience VARCHAR(1000);"))
                print("Added column 'experience' to 'teachers' table.")
            else:
                print("Column 'experience' already exists.")
                
            if 'photo_path' not in teachers_cols:
                conn.execute(text("ALTER TABLE teachers ADD COLUMN photo_path VARCHAR(255);"))
                print("Added column 'photo_path' to 'teachers' table.")
            else:
                print("Column 'photo_path' already exists.")
    except Exception as e:
        print("Error modifying teachers table:", e)

    try:
        centers_cols = [col['name'] for col in inspector.get_columns('centers')]
        with engine.begin() as conn:
            if 'bot_username' not in centers_cols:
                conn.execute(text("ALTER TABLE centers ADD COLUMN bot_username VARCHAR(255);"))
                print("Added column 'bot_username' to 'centers' table.")
            else:
                print("Column 'bot_username' already exists.")
    except Exception as e:
        print("Error modifying centers table:", e)

if __name__ == '__main__':
    add_columns()
