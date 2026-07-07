"""
categories jadvalini yaratadi va mavjud kurslardan categoriyalarni import qiladi.
"""
import os
from sqlalchemy import create_engine, text

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_URL = f'sqlite:///{os.path.join(BASE_DIR, "crm.db")}'
engine = create_engine(DB_URL)

def run():
    with engine.connect() as conn:
        # 1. categories jadvalini yaratish
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(100) NOT NULL UNIQUE
            )
        """))

        # 2. mavjud kurslardan unikal kategoriyalarni olish va qo'shish
        rows = conn.execute(text("SELECT DISTINCT category FROM courses WHERE category IS NOT NULL AND category != ''")).fetchall()
        for row in rows:
            cat_name = row[0]
            exists = conn.execute(text("SELECT id FROM categories WHERE name = :name"), {"name": cat_name}).fetchone()
            if not exists:
                conn.execute(text("INSERT INTO categories (name) VALUES (:name)"), {"name": cat_name})
                print(f"  + Bo'lim qo'shildi: {cat_name}")
            else:
                print(f"  ~ Allaqachon bor: {cat_name}")

        conn.commit()
        print("Migrasyon tugadi!")

if __name__ == '__main__':
    run()
