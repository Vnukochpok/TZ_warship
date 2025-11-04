from fastapi import FastAPI

from app.db_connect.db import engine
from app.db_models.base import Base
from app.api import players, games, websocket

app = FastAPI(title="Warship API")

# подключаю роутеры
app.include_router(players.router)
app.include_router(games.router)
app.include_router(websocket.router)

# lalala
# подключение к бд
@app.on_event("startup")
async def startup_event():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Подключение прошло успешно")

@app.get("/")
async def home_page():
    return {"message": "Игра морской бой"}