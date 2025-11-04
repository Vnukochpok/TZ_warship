from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.db_connect.db import get_db
from app.services.player_service import PlayerService
from app.schemas.players import PlayerCreate, PlayerLogin, Player, PlayerStats

router = APIRouter(prefix="/players", tags=["Players"])

# эндпоинт для регистрации игркоа
@router.post("/register", response_model=Player)
async def register_player(
    player_data: PlayerCreate,
    db: AsyncSession = Depends(get_db)
):
    created_player_orm = await PlayerService.register_player(db, player_data)
    if created_player_orm is None:
        raise HTTPException(status_code=400, detail="Игрок с таким логином уже существует")
    return Player.model_validate(created_player_orm)

# эндпоинт для авторизации игрока
@router.post("/login", response_model=Player)
async def login_player(
    player_data: PlayerLogin,
    db: AsyncSession = Depends(get_db)
):
    logged_in_player_orm = await PlayerService.login_player(db, player_data)
    if logged_in_player_orm is None:
        raise HTTPException(status_code=400, detail="Неверный логин или пароль")
    return Player.model_validate(logged_in_player_orm)

# эндпоинт для получения всех игроков, доступных для игры (статус = 0)
@router.get("/", response_model=List[Player])
async def get_available_players(db: AsyncSession = Depends(get_db)):
    players_pydantic = await PlayerService.get_available_players(db)
    return players_pydantic

# эндпоинт для получения статистики игрока
@router.get("/{player_id}/stats", response_model=PlayerStats)
async def get_player_stats_endpoint(player_id: int, db: AsyncSession = Depends(get_db)):
    stats = await PlayerService.get_player_stats(db, player_id)
    if stats.login == "Unknown":
        raise HTTPException(status_code=404, detail=f"Игрок с ID {player_id} не найден")
    return stats