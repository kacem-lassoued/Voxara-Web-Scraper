from sqlalchemy import Column, String, Boolean, ForeignKey, Enum, Time, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
import uuid
import enum
from app.core.database import Base

class UserRole(str, enum.Enum):
    student = "student"
    admin = "admin"
    super_admin = "super_admin"

class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, index=True)
    password_hash = Column(String)
    role = Column(Enum(UserRole), default=UserRole.student)
    is_active = Column(Boolean, default=True)

class Timetable(Base):
    __tablename__ = "timetables"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    uploader_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    file_url = Column(String)
    semester = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_updated = Column(DateTime(timezone=True), onupdate=func.now())
    reviewed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

class TimetableSlot(Base):
    __tablename__ = "timetable_slots"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    timetable_id = Column(UUID(as_uuid=True), ForeignKey("timetables.id"))
    day = Column(String)
    start_time = Column(Time)
    end_time = Column(Time)
    course_name = Column(String, index=True)
    teacher_name = Column(String, index=True)
    room = Column(String)