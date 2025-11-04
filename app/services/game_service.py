from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
import random
import json
from datetime import datetime
from typing import List, Optional, Tuple

from app.db_models.players import PlayersORM
from app.db_models.games import GamesORM
from app.schemas.games import GameWithPlayerLogins
from app.services.player_service import PlayerService

# натсройки игры, упрощенная версия морского боя: 3 корабля длиной в 3 клетки
BOARD_SIZE = 10
NUM_SHIPS = 3
SHIP_LENGTH = 3

class GameService:

    @staticmethod
    def generate_random_board() -> str:
        # генерирую доски для игры, 0 - поустая клетка, 1 - корабль
        board = [[0 for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]
        placed_ships_cells = []

        attempts = 0
        max_attempts = 1000

        # логика рандомного расположения корабля по правилам игры
        while len(placed_ships_cells) < NUM_SHIPS * SHIP_LENGTH and attempts < max_attempts:
            ship_cells = []

            # выбор ориентации: горизонтальная или вертикальная
            orientation = random.choice(['horizontal', 'vertical'])

            if orientation == 'horizontal':
                row = random.randint(0, BOARD_SIZE - 1)
                col = random.randint(0, BOARD_SIZE - SHIP_LENGTH)
                potential_cells = [(row, col + i) for i in range(SHIP_LENGTH)]
            else:
                row = random.randint(0, BOARD_SIZE - SHIP_LENGTH)
                col = random.randint(0, BOARD_SIZE - 1)
                potential_cells = [(row + i, col) for i in range(SHIP_LENGTH)]

            # Проверяю, заняты ли клетки
            collision = False
            for r, c in potential_cells:
                if board[r][c] == 1:
                    collision = True
                    break
                # проверяю соседние клетки
                for dr in [-1, 0, 1]:
                    for dc in [-1, 0, 1]:
                        nr, nc = r + dr, c + dc
                        if (0 <= nr < BOARD_SIZE and 0 <= nc < BOARD_SIZE and
                            board[nr][nc] == 1 and (nr, nc) not in potential_cells):
                            collision = True
                            break
                    if collision: break
                if collision: break

            if not collision:
                for r, c in potential_cells:
                    board[r][c] = 1
                    placed_ships_cells.append((r, c))
            attempts += 1

        if len(placed_ships_cells) < NUM_SHIPS * SHIP_LENGTH:
            # если не удалось разместить все корабли после max_attempts
            raise RuntimeError("Не удалось разместить все корабли")


        # возвращаю доску как JSON строку
        return json.dumps(board)

    @staticmethod
    async def create_game(db: AsyncSession, player1_id: int, player2_id: int) -> Optional[GamesORM]:
        player1 = await db.get(PlayersORM, player1_id)
        player2 = await db.get(PlayersORM, player2_id)

        # один из игроков не найден
        if not player1 or not player2:
            return None
        # один из игроков уже играет
        if player1.status == 1 or player2.status == 1:
            return None
        # игроки не могут быть одни и те же
        if player1_id == player2_id:
            return None

        # обновляю статус игроков на 1 (играют)
        player1.status = 1
        player2.status = 1
        db.add(player1)
        db.add(player2)

        # генерирую доски
        try:
            board1_json = GameService.generate_random_board()
            board2_json = GameService.generate_random_board()
        except RuntimeError as e:
            # если генерация доски не удалась, снова меняю статусов и возвращаю None
            player1.status = 0
            player2.status = 0
            await db.commit()
            return None

        new_game = GamesORM(
            player_1_id=player1_id,
            player_2_id=player2_id,
            p_1_res=0,
            p_2_res=0,
            online=True,
            start_date=datetime.utcnow(),
            board_player_1=board1_json,
            board_player_2=board2_json,
            current_turn_player_id=player1_id
        )

        db.add(new_game)
        await db.commit()
        await db.refresh(new_game)
        return new_game

    @staticmethod
    async def get_active_games(db: AsyncSession) -> List[GameWithPlayerLogins]:
        # получаю все активные игры
        stmt_games = select(GamesORM).where(GamesORM.online == True)
        result_games = await db.execute(stmt_games)
        active_games_orm = result_games.scalars().all()

        if not active_games_orm:
            return []

        # собираю id игроков в онлайн играх
        player_ids = set()
        for game in active_games_orm:
            player_ids.add(game.player_1_id)
            player_ids.add(game.player_2_id)

        stmt_players = select(PlayersORM).where(PlayersORM.id.in_(player_ids))
        result_players = await db.execute(stmt_players)
        players_orm_map = {player.id: player for player in result_players.scalars()}

        # составляю результат и вывожу
        games_with_logins = []
        for game in active_games_orm:
            player1 = players_orm_map.get(game.player_1_id)
            player2 = players_orm_map.get(game.player_2_id)

            if player1 and player2:
                games_with_logins.append(GameWithPlayerLogins(
                    id=game.id,
                    player_1_login=player1.login,
                    player_2_login=player2.login,
                    p_1_res=game.p_1_res,
                    p_2_res=game.p_2_res,
                    online=game.online,
                    start_date=game.start_date
                ))

        return games_with_logins

    @staticmethod
    async def get_game_by_id(db: AsyncSession, game_id: int) -> Optional[GamesORM]:
        return await db.get(GamesORM, game_id)

    @staticmethod
    async def update_game_status(db: AsyncSession, game_id: int, is_online: bool):
        game = await db.get(GamesORM, game_id)
        if game:
            game.online = is_online
            await db.commit()
            await db.refresh(game)
            return game
        return None

    @staticmethod
    async def process_player_move(
        db: AsyncSession,
        game_id: int,
        player_id: int,
        target_row: int,
        target_col: int
    ) -> Tuple[str, Optional[str], Optional[str]]:

        game = await GameService.get_game_by_id(db, game_id)
        if not game or not game.online:
            return "Игра не найдена или завершена", None, None

        player1 = await db.get(PlayersORM, game.player_1_id)
        player2 = await db.get(PlayersORM, game.player_2_id)

        if not player1 or not player2:
            return "Ошибка: один из игроков не найден", None, None

        if player_id == game.player_1_id:
            is_player1_turn = True
            my_board_json = game.board_player_1
            target_board_json = game.board_player_2
            my_res_attr = 'p_1_res'
            opponent_res_attr = 'p_2_res'
        elif player_id == game.player_2_id:
            is_player1_turn = False
            my_board_json = game.board_player_2
            target_board_json = game.board_player_1
            my_res_attr = 'p_2_res'
            opponent_res_attr = 'p_1_res'

        # проверяю чей сейчас ход
        current_player_moved_id = player_id

        if game.player_1_id == current_player_moved_id:
            game.current_turn_player_id = game.player_2_id
        else:
            game.current_turn_player_id = game.player_1_id

        if player_id != game.current_turn_player_id:
            return "Сейчас не ваш ход!", None, None

        # получаю JSON доску
        try:
            my_board = json.loads(my_board_json)
            target_board = json.loads(target_board_json)
        except (json.JSONDecodeError, TypeError):
            return "Ошибка получения доски", None, None

        # проверяю, что ход сделан по правильным координатам
        if not (0 <= target_row < BOARD_SIZE and 0 <= target_col < BOARD_SIZE):
            return "Некорректные координаты выстрела.", None, None

        # проверяю, в свободную ли клетку выстрелил игрок
        # 0 - пусто (промах), 1 - корабль (попадание), 2 - повторное попадание, 3 повторный промах - промах
        cell_value = target_board[target_row][target_col]
        if cell_value == 2:
            return "В эту клетку уже было попадание", None, None
        if cell_value == 3:
            return "В эту клетку уже был промах", None, None

        # обработка выстрела
        result_message = ""
        is_hit = False
        is_sunk = False
        all_ships_sunk = False

        # отмечаю попадание по кораблю
        if cell_value == 1:
            target_board[target_row][target_col] = 2
            result_message = "Попадание"
            is_hit = True

            # проверяю, потоплен ли корабль
            if GameService.is_ship_sunk(target_board, target_row, target_col):
                result_message += " Корабль потоплен"
                is_sunk = True

                # проверяем окончание игры
                if GameService.are_all_ships_sunk(target_board):
                    result_message += " Все ваши корабли уничтожены"
                    all_ships_sunk = True
                    game.online = False
                    # игрок, чей ход был посдедним, проиграл (его корабли потоплены)
                    setattr(game, my_res_attr, 0)
                    setattr(game, opponent_res_attr, 1)
                    # обновляю статусы игроков
                    player1.status = 0
                    player2.status = 0
                    db.add(player1)
                    db.add(player2)
        # промах по кораблю
        else:
            target_board[target_row][target_col] = 3
            result_message = "Промах"

        # обновляю доски в базе данных
        if is_player1_turn:
            game.board_player_1 = json.dumps(my_board)
            game.board_player_2 = json.dumps(target_board)
        else:
            game.board_player_2 = json.dumps(my_board)
            game.board_player_1 = json.dumps(target_board)

        await db.commit()
        await db.refresh(game)

        # обновляю статистику игроков, если игра завершена
        if all_ships_sunk:
            await PlayerService.update_player_stats(db, game, player1.id)
            await PlayerService.update_player_stats(db, game, player2.id)

        # возвращаю JSON доски для отображения на клиенте
        return result_message, json.dumps(my_board), json.dumps(target_board)


    # функция для проверки, потоплен ли корабль
    @staticmethod
    def is_ship_sunk(board: List[List[int]], row: int, col: int) -> bool:
        # перепроверяю, что в клетке было попадание
        if board[row][col] != 2:
            return False

        # для того, чтобы понять, потоплен ли корабль, я проверяю соседние клетки, чтобы найти остальные части от этого корабля
        # если остальные части тоже были подбиты, то корабль потоплен
        q = [(row, col)]
        visited = set([(row, col)])
        ship_cells_found = []

        while q:
            r, c = q.pop(0)

            # добавляю текущую клетку, если она является частью корабля
            if board[r][c] in [1, 2]:
                ship_cells_found.append((r, c))

            # просматриваю соседние клетки
            for dr in [-1, 0, 1]:
                for dc in [-1, 0, 1]:
                    # проверяю только гориз. и верт. клетки
                    if abs(dr) + abs(dc) == 1:
                        nr, nc = r + dr, c + dc
                        if 0 <= nr < BOARD_SIZE and 0 <= nc < BOARD_SIZE:
                            if (nr, nc) not in visited and board[nr][nc] in [1, 2]:
                                visited.add((nr, nc))
                                q.append((nr, nc))

        # проверяею, есть ли в найденных клетках значение 1
        for r, c in ship_cells_found:
            if board[r][c] == 1:
                return False

        return True

    # функция для првоерки, все ли корабли потоплены
    @staticmethod
    def are_all_ships_sunk(board: List[List[int]]) -> bool:
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                # если есть хотя бы одна целая часть корабля
                if board[r][c] == 1:
                    return False
        return True
