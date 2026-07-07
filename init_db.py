import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base, Admin, Center
from werkzeug.security import generate_password_hash
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_URL = f'sqlite:///{os.path.join(BASE_DIR, "crm.db")}'

engine = create_engine(DB_URL)
Session = sessionmaker(bind=engine)

def init_db():
    Base.metadata.create_all(engine)
    session = Session()
    
    # Super Admin
    if not session.query(Admin).filter_by(username='superadmin').first():
        session.add(Admin(
            username='superadmin',
            password_hash=generate_password_hash('superadmin123'),
            role='superadmin',
            full_name='Super Administrator'
        ))
        print("Super Admin created: superadmin / superadmin123")

    # Default Center 1
    center = session.query(Center).filter_by(name="O'quv Markazi 1").first()
    if not center:
        # Check env for bot token
        bot_token = os.getenv("BOT_TOKEN", "7892142365:AAHh3j8ESs8ibVqhPk-Wmx5sbpSyYEZDQK0")
        center = Center(name="O'quv Markazi 1", telegram_bot_token=bot_token)
        session.add(center)
        session.flush()
        print(f"Default Center created: {center.name} (Bot: {bot_token})")
    
    # Manager for Center 1
    if not session.query(Admin).filter_by(username='manager').first():
        session.add(Admin(
            username='manager', 
            password_hash=generate_password_hash('manager123'),
            role='manager',
            full_name='Manager 1',
            center_id=center.id
        ))
        print("Manager created: manager / manager123")
    
    # Director for Center 1
    if not session.query(Admin).filter_by(username='director').first():
        session.add(Admin(
            username='director', 
            password_hash=generate_password_hash('director123'),
            role='director',
            full_name='Markaz Direktori 1',
            center_id=center.id
        ))
        print("Director created: director / director123")
    
    session.commit()
    session.close()
    print("Database inited successfully!")

if __name__ == "__main__":
    init_db()
