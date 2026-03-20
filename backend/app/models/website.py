from datetime import datetime
from ..extensions import db
from sqlalchemy.orm import Mapped, mapped_column

class Website(db.Model):
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    url: Mapped[str] = mapped_column(unique=True)
    status: Mapped[str] = mapped_column(default="active")
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "url": self.url,
            "status": self.status,
            "created_at": self.created_at,
        }