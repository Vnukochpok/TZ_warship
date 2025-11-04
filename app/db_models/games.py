from sqlalchemy import Integer, String, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from .base import Base

class GamesORM(Base):
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(primary_key=True)
    player_1_id: Mapped[int] = mapped_column(Integer)
    player_2_id: Mapped[int] = mapped_column(Integer)
    p_1_res: Mapped[int] = mapped_column(Integer, default=0)
    p_2_res: Mapped[int] = mapped_column(Integer, default=0)
    online: Mapped[bool] = mapped_column(Boolean, default=True)
    start_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    board_player_1: Mapped[str] = mapped_column(String, nullable=True)
    board_player_2: Mapped[str] = mapped_column(String, nullable=True)
    current_turn_player_id: Mapped[int] = mapped_column(Integer)