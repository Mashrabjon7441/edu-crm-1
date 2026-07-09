import os
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL", f'sqlite:///crm.db')
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)

def add_columns():
    with engine.begin() as conn:
        is_postgres = 'postgresql' in DATABASE_URL
        if is_postgres:
            check_query = """
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='teachers';
            """
        else:
            check_query = "PRAGMA table_info(teachers);"
            
        columns = [row[0] if is_postgres else row[1] for row in conn.execute(text(check_query)).fetchall()]
        
        if 'experience' not in columns:
            conn.execute(text("ALTER TABLE teachers ADD COLUMN experience VARCHAR(1000);"))
            print("Added column 'experience' to 'teachers' table.")
        else:
            print("Column 'experience' already exists.")
            
        if 'photo_path' not in columns:
            conn.execute(text("ALTER TABLE teachers ADD COLUMN photo_path VARCHAR(255);"))
            print("Added column 'photo_path' to 'teachers' table.")
        else:
            print("Column 'photo_path' already exists.")

        # Check centers table
        if is_postgres:
            check_centers = """
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='centers';
            """
        else:
            check_centers = "PRAGMA table_info(centers);"
        centers_cols = [row[0] if is_postgres else row[1] for row in conn.execute(text(check_centers)).fetchall()]
        if 'bot_username' not in centers_cols:
            conn.execute(text("ALTER TABLE centers ADD COLUMN bot_username VARCHAR(255);"))
            print("Added column 'bot_username' to 'centers' table.")
        else:
            print("Column 'bot_username' already exists.")

if __name__ == '__main__':
    add_columns()
