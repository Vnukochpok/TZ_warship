from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.db_connect.db import get_db
from app.services.game_service import GameService
from app.services.player_service import PlayerService
from app.schemas.games import GameCreate, Game, GameWithPlayerLogins

router = APIRouter(prefix="/games", tags=["Games"])

# эндпоинт для создания комнаты игры
@router.post("/create", response_model=Game)
async def create_game(
    game_data: GameCreate,
    db: AsyncSession = Depends(get_db)
):
    player1_orm = await PlayerService.get_player_by_id(db, game_data.player_1_id)
    player2_orm = await PlayerService.get_player_by_id(db, game_data.player_2_id)

    # проверяю что игроки есть и они не играют
    if not player1_orm or not player2_orm:
        raise HTTPException(status_code=404, detail="Один или оба игрока не найдены")
    if player1_orm.status == 1 or player2_orm.status == 1:
        raise HTTPException(status_code=400, detail="Один или оба игрока уже играют")
    if game_data.player_1_id == game_data.player_2_id:
        raise HTTPException(status_code=400, detail="Игроки не могут быть одни и те же")

    # создаю комнату игры
    new_game_orm = await GameService.create_game(db, game_data.player_1_id, game_data.player_2_id)
    if new_game_orm is None:
        raise HTTPException(status_code=500, detail="Не удалось создать игру")

    return Game.model_validate(new_game_orm)

# эндпоинт для получения активных игр
@router.get("/", response_model=List[GameWithPlayerLogins])
async def get_active_games(db: AsyncSession = Depends(get_db)):
    games_with_logins = await GameService.get_active_games(db)
    return games_with_logins