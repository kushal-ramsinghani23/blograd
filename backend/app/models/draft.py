from datetime import datetime
from ..extensions import db
from sqlalchemy.orm import Mapped, mapped_column

class Draft(db.Model):
    __tablename__ = 'drafts'

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
    content: Mapped[str]
    image_path: Mapped[str | None] = mapped_column(default=None)
    source_url: Mapped[str]
    matched_keywords: Mapped[str | None] = mapped_column(default=None)
    status: Mapped[str] = mapped_column(default='draft')
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'content': self.content,
            'image_path': self.image_path,
            'source_url': self.source_url,
            'matched_keywords': self.matched_keywords,
            'status': self.status,
            'created_at': self.created_at,
        }