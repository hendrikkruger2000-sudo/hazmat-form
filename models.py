from sqlalchemy import Column, String, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()

class Assignment(Base):
    __tablename__ = "assignments"
    hazjnb_ref = Column(String, primary_key=True)
    driver_code = Column(String)

engine = create_engine("sqlite:///hazmat.db")
SessionLocal = sessionmaker(bind=engine)
Base.metadata.create_all(engine)