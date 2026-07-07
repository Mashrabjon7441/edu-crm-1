from sqlalchemy import create_engine
from models import Base
from init_db import init_db

engine = create_engine('sqlite:///crm.db')

def recreate():
    Base.metadata.drop_all(engine)
    init_db()

if __name__ == '__main__':
    recreate()
