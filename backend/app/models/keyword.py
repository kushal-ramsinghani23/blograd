from datetime import datetime
from ..extensions import db
from sqlalchemy.orm import Mapped, mapped_column

class Keyword(db.Model):
    __tablename__ = "keywords"

    id: Mapped[int] = mapped_column(primary_key=True)
    word: Mapped[str] = mapped_column(unique=True)
    category: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "word": self.word,
            "category": self.category,
            "created_at": self.created_at
        }
