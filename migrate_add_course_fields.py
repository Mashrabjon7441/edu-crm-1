import os
from sqlalchemy import create_engine, text

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_URL = f'sqlite:///{os.path.join(BASE_DIR, "crm.db")}'
engine = create_engine(DB_URL)

def column_exists(column_name):
    with engine.connect() as conn:
        result = conn.execute(text(f"PRAGMA table_info(courses);")).fetchall()
        return any(row[1] == column_name for row in result)

def add_column(column_def):
    with engine.connect() as conn:
        conn.execute(text(f"ALTER TABLE courses ADD COLUMN {column_def};"))
        print(f"Added column: {column_def}")

if __name__ == '__main__':
    if not column_exists('category'):
        add_column("category TEXT NOT NULL DEFAULT 'Dasturlash'")
    else:
        print('Column category already exists')
    if not column_exists('days'):
        add_column("days TEXT NOT NULL DEFAULT 'dushanba,chorshanba,juma'")
    else:
        print('Column days already exists')
