from sqlalchemy import Column, Integer, BigInteger, String, DateTime, ForeignKey, Date
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime, date
from flask_login import UserMixin

Base = declarative_base()

class Center(Base):
    __tablename__ = 'centers'
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    telegram_bot_token = Column(String(255), nullable=True)
    bot_username = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Category(Base):
    __tablename__ = 'categories'
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    center_id = Column(Integer, ForeignKey('centers.id'), nullable=True)

    center = relationship('Center', backref='categories')

class Admin(Base, UserMixin):
    __tablename__ = 'admins'
    id = Column(Integer, primary_key=True)
    username = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False) # 'superadmin', 'director', 'manager'
    full_name = Column(String(255), nullable=True)
    center_id = Column(Integer, ForeignKey('centers.id'), nullable=True)

    center = relationship('Center', backref='admins')

    def get_id(self):
        return f"admin:{self.id}"

class Teacher(Base, UserMixin):
    __tablename__ = 'teachers'
    id = Column(Integer, primary_key=True)
    full_name = Column(String(255), nullable=False)
    subject = Column(String(100), nullable=False)
    qualification = Column(String(255), nullable=True)
    username = Column(String(100), unique=True, nullable=True)
    password_hash = Column(String(255), nullable=True)
    role = Column(String(50), default='teacher')
    center_id = Column(Integer, ForeignKey('centers.id'), nullable=True)
    experience = Column(String(1000), nullable=True)
    photo_path = Column(String(255), nullable=True)

    center = relationship('Center', backref='teachers')
    courses = relationship('Course', back_populates='teacher')

    def get_id(self):
        return f"teacher:{self.id}"

class Course(Base):
    __tablename__ = 'courses'
    id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False)
    teacher_id = Column(Integer, ForeignKey('teachers.id'), nullable=True)
    start_date = Column(String(50), nullable=False)
    schedule_time = Column(String(50), nullable=False)
    category = Column(String(100), nullable=False)
    days = Column(String(50), nullable=False, default='dushanba,chorshanba,juma')
    max_students = Column(Integer, default=15)
    current_students = Column(Integer, default=0)
    status = Column(String(50), default='active')
    center_id = Column(Integer, ForeignKey('centers.id'), nullable=True)

    center = relationship('Center', backref='courses')
    teacher = relationship('Teacher', back_populates='courses')
    enrollments = relationship('Enrollment', back_populates='course')

    @property
    def accepted_students_count(self):
        return sum(1 for e in self.enrollments if e.status == 'accepted')

class Student(Base):
    __tablename__ = 'students'
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, nullable=True) # removed unique to support registering in multiple centers
    full_name = Column(String(255), nullable=False)
    phone_number = Column(String(20), nullable=False)
    center_id = Column(Integer, ForeignKey('centers.id'), nullable=True)
    added_by = Column(String(100), nullable=True, default='Telegram Bot')

    center = relationship('Center', backref='students')
    enrollments = relationship('Enrollment', back_populates='student')

    @property
    def phone(self):
        return self.phone_number

class Enrollment(Base):
    __tablename__ = 'enrollments'
    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey('students.id'), nullable=False)
    course_id = Column(Integer, ForeignKey('courses.id'), nullable=False)
    status = Column(String(50), default='waitlisted') 
    callback_date = Column(Date, nullable=True)
    joined_date = Column(Date, nullable=True)
    next_payment_date = Column(Date, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    student = relationship('Student', back_populates='enrollments')
    course = relationship('Course', back_populates='enrollments')

class Attendance(Base):
    __tablename__ = 'attendance'
    id = Column(Integer, primary_key=True)
    course_id = Column(Integer, ForeignKey('courses.id'), nullable=False)
    student_id = Column(Integer, ForeignKey('students.id'), nullable=False)
    date = Column(Date, default=date.today)
    is_present = Column(Integer, default=1)

    course = relationship('Course')
    student = relationship('Student')

class ActivityLog(Base):
    __tablename__ = 'activity_logs'
    id = Column(Integer, primary_key=True)
    center_id = Column(Integer, ForeignKey('centers.id'), nullable=False)
    user_name = Column(String(255), nullable=False)
    user_role = Column(String(50), nullable=False)
    action = Column(String(100), nullable=False)
    details = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    center = relationship('Center', backref='activity_logs')
