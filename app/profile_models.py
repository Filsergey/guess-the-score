import json
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    avatar_data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    avatar_media_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    oracle_style: Mapped[str] = mapped_column(String(32), default="irony")
    notification_preferences: Mapped[str] = mapped_column(Text, default="{}")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def notification_timezone(self) -> str:
        try:
            raw=json.loads(self.notification_preferences or '{}')
            value=str(raw.get('_timezone') or '').strip()
            return value or 'Europe/Moscow'
        except Exception:
            return 'Europe/Moscow'
