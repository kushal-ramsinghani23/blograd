from datetime import datetime
from .. import db
from sqlalchemy.orm import Mapped, mapped_column

class Website(db.Model):
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    url: Mapped[str] = mapped_column(unique=True)
    status: Mapped[str] = mapped_column(default="active")
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
