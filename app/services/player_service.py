from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List, Optional

from app.db_models.players import PlayersORM
from app.db_models.games import GamesORM
from app.schemas.players import PlayerCreate, PlayerLogin, Player, PlayerStats

class PlayerService:
    @staticmethod
    async def register_player(db: AsyncSession, player_data: PlayerCreate) -> Optional[PlayersORM]:
        # проверяю существование игрока в бд
        stmt_check = select(PlayersORM).where(PlayersORM.login == player_data.login)
        result = await db.execute(stmt_check)
        existing_player = result.scalar_one_or_none()

        if existing_player:
            return None

        new_player_orm = PlayersORM(
            login=player_data.login,
            password=player_data.password,
            stats=0,
            status=0
        )
        db.add(new_player_orm)
        await db.commit()
        await db.refresh(new_player_orm)
        return new_player_orm

    @staticmethod
    async def login_player(db: AsyncSession, player_data: PlayerLogin) -> Optional[PlayersORM]:
        # через select смотрю есть ли пользователь в бд
        stmt = select(PlayersORM).where(PlayersORM.login == player_data.login)
        result = await db.execute(stmt)
        player = result.scalar_one_or_none()

        # сравниваю пароли пользователя
        if player and player.password == player_data.password:
            await db.commit()
            await db.refresh(player)
            return player
        return None

    @staticmethod
    async def logout_player(db: AsyncSession, player_id: int):
        # получаю игрока по id
        player = await db.get(PlayersORM, player_id)
        if player:
            player.status = 0
            await db.commit()
            await db.refresh(player)

    @staticmethod
    async def get_available_players(db: AsyncSession) -> List[Player]:
        # также через select выбираю игроков, у которых статус = 0
        stmt = select(PlayersORM).where(PlayersORM.status == 0)
        result = await db.execute(stmt)
        players_orm = result.scalars().all()
        return [Player.model_validate(p) for p in players_orm]

    @staticmethod
    async def get_player_by_id(db: AsyncSession, player_id: int) -> Optional[PlayersORM]:
        player = await db.get(PlayersORM, player_id)
        return player

    @staticmethod
    async def update_player_stats(db: AsyncSession, game: GamesORM, player_id: int):
        player = await PlayerService.get_player_by_id(db, player_id)
        if not player:
            return

        # по p_1\2_res определяю, кто победил в игре
        is_winner = False
        if game.player_1_id == player_id and game.p_1_res == 1:
            is_winner = True
        elif game.player_2_id == player_id and game.p_2_res == 1:
            is_winner = True

        # обновляю данные
        player.stats += 1 if is_winner else -1
        await db.commit()
        await db.refresh(player)

    @staticmethod
    async def get_player_stats(db: AsyncSession, player_id: int) -> PlayerStats:
        player_orm = await PlayerService.get_player_by_id(db, player_id)
        if not player_orm:
            return PlayerStats(id=player_id, login="Unknown", total_games=0, wins=0, losses=0)

        # для получения игр, где участвовал игрок использую player_1\2_id, с усл оператором ИЛИ
        stmt_games = select(GamesORM).where(
            (GamesORM.player_1_id == player_id) | (GamesORM.player_2_id == player_id)
        )
        result_games = await db.execute(stmt_games)
        all_games = result_games.scalars().all()

        total_games = len(all_games)
        wins = 0
        losses = 0

        # опеределяю победы и проигрыши игрока
        for game in all_games:
            if game.player_1_id == player_id:
                if game.p_1_res == 1:
                    wins += 1
                else:
                    losses += 1
            elif game.player_2_id == player_id:
                if game.p_2_res == 1:
                    wins += 1
                else:
                    losses += 1

        return PlayerStats(
            id=player_orm.id,
            login=player_orm.login,
            total_games=total_games,
            wins=wins,
            losses=losses
        )