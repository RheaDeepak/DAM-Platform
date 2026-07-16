from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from app.database import Base


class AuditAction(str, enum.Enum):
    UPLOADED = "uploaded"
    VIEWED = "viewed"
    MODIFIED = "modified"
    DELETED = "deleted"
    SHARED = "shared"
    DOWNLOADED = "downloaded"
    APPROVED = "approved"
    REJECTED = "rejected"
    ARCHIVED = "archived"
    RESTORED = "restored"
    TAGGED = "tagged"
    UNTAGGED = "untagged"


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    action = Column(Enum(AuditAction), index=True)
    details = Column(Text, nullable=True)
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    # Relationships
    asset = relationship("Asset", back_populates="audit_logs")
    user = relationship("User", back_populates="audit_logs")
