"""
db/models.py — SQLAlchemy ORM models v2
Includes: late arrival, photo capture, needs_reregistration
"""

from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Date,
    Float, Enum, ForeignKey, UniqueConstraint, Index, Time
)
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    username      = Column(String(50),  nullable=False, unique=True)
    email         = Column(String(100), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)
    role          = Column(Enum("admin", "teacher"), nullable=False, default="teacher")
    is_active     = Column(Boolean, nullable=False, default=True)
    created_at    = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_login    = Column(DateTime, nullable=True)

    subjects = relationship("Subject", back_populates="teacher", lazy="dynamic")

    @property
    def is_authenticated(self): return True
    @property
    def is_anonymous(self): return False
    def get_id(self): return str(self.id)

    def __repr__(self):
        return f"<User {self.username!r} role={self.role}>"


class Subject(Base):
    __tablename__ = "subjects"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    name             = Column(String(100), nullable=False)
    code             = Column(String(20),  nullable=False, unique=True)
    teacher_id       = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    class_start_time = Column(Time, nullable=True)   # e.g. 08:00:00
    class_end_time   = Column(Time, nullable=True)
    is_active        = Column(Boolean, nullable=False, default=True)
    created_at       = Column(DateTime, nullable=False, default=datetime.utcnow)

    teacher    = relationship("User", back_populates="subjects")
    attendance = relationship("Attendance", back_populates="subject", lazy="dynamic")

    def __repr__(self):
        return f"<Subject {self.code}: {self.name!r}>"


class Student(Base):
    __tablename__ = "students"

    id                   = Column(Integer, primary_key=True, autoincrement=True)
    reg_number           = Column(String(30),  nullable=False, unique=True)
    name                 = Column(String(100), nullable=False)
    email                = Column(String(100), nullable=True)
    class_name           = Column(String(50),  nullable=True)
    dataset_path         = Column(String(255), nullable=True)
    is_encoded           = Column(Boolean, nullable=False, default=False)
    needs_reregistration = Column(Boolean, nullable=False, default=False)
    is_active            = Column(Boolean, nullable=False, default=True)
    created_at           = Column(DateTime, nullable=False, default=datetime.utcnow)

    attendance = relationship("Attendance", back_populates="student", lazy="dynamic")

    def __repr__(self):
        return f"<Student {self.reg_number}: {self.name!r}>"


class Attendance(Base):
    __tablename__ = "attendance"
    __table_args__ = (
        UniqueConstraint("student_id", "subject_id", "marked_date",
                         name="unique_daily_attendance"),
        Index("idx_att_student", "student_id"),
        Index("idx_att_subject", "subject_id"),
    )

    id          = Column(Integer, primary_key=True, autoincrement=True)
    student_id  = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    subject_id  = Column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False)
    marked_at   = Column(DateTime, nullable=False, default=datetime.utcnow)
    marked_date = Column(Date,     nullable=False, default=date.today)
    confidence  = Column(Float,    nullable=False)
    status      = Column(Enum("present", "late", "manual"), nullable=False, default="present")
    photo_path  = Column(String(255), nullable=True)

    student = relationship("Student", back_populates="attendance")
    subject = relationship("Subject", back_populates="attendance")

    def __repr__(self):
        return f"<Attendance student={self.student_id} date={self.marked_date} status={self.status}>"
