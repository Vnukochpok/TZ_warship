from sqlalchemy.orm import DeclarativeBase
from app.db_connect.db import engine

class Base(DeclarativeBase):
    def __repr__(self):
        if self.__mapper__ and self.__mapper__.column_attrs:
            attrs = ", ".join(f"{col}={getattr(self, col)!r}" for col in self.__mapper__.column_attrs.keys())
            return f"<{self.__class__.__name__}({attrs})>"
        else:
            return f"<{self.__class__.__name__}()>"

Base.metadata.bind = engine