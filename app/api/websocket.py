from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.ext.asyncio import AsyncSession
import json
from typing import List, Dict, Optional

from app.db_connect.db import get_db
from app.services.game_service import GameService
from app.services.player_service import PlayerService
from app.db_models.players import PlayersORM


router = APIRouter()

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[int, List[WebSocket]] = {}

    # функции для вебсокета: подключение, отключение, отправка сообщений
    async def connect(self, websocket: WebSocket, game_id: int):
        await websocket.accept()
        if game_id not in self.active_connections:
            self.active_connections[game_id] = []
        self.active_connections[game_id].append(websocket)

    def disconnect(self, websocket: WebSocket, game_id: int):
        if game_id in self.active_connections:
            if websocket in self.active_connections[game_id]:
                self.active_connections[game_id].remove(websocket)
            if not self.active_connections[game_id]:
                del self.active_connections[game_id]

    async def broadcast(self, message: str, game_id: int, sender_websocket: WebSocket = None):
        if game_id in self.active_connections:
            for connection in self.active_connections[game_id]:
                if connection != sender_websocket:
                    await connection.send_text(message)

    async def broadcast_to_all_in_game(self, message: str, game_id: int):
        if game_id in self.active_connections:
            for connection in self.active_connections[game_id]:
                await connection.send_text(message)

manager = ConnectionManager()

# эндпоинт для вебсокета
@router.websocket("/games/{game_id}/play")
async def websocket_game_play(
    websocket: WebSocket,
    game_id: int,
    db: AsyncSession = Depends(get_db)
):
    # сначала делаю проверку на состояние игры
    game = await GameService.get_game_by_id(db, game_id)
    if not game or not game.online:
        await websocket.close(code=1008, reason="Игра не найдена или завершена")
        return

    player1_id = game.player_1_id
    player2_id = game.player_2_id

    # получаю orm игроков
    player1_orm = await db.get(PlayersORM, player1_id)
    player2_orm = await db.get(PlayersORM, player2_id)

    if not player1_orm or not player2_orm:
        await websocket.close(code=1008, reason="Ошибка: Один из игроков не найден")
        return

    await manager.connect(websocket, game_id)

    player_id_making_call: Optional[int] = None
    my_player_orm: Optional[PlayersORM] = None
    is_player1_in_game: bool = False

    try:
        # идентифицирую игроков
        auth_message = await websocket.receive_json()
        if auth_message.get("type") == "auth" and "player_id" in auth_message:
            player_id_making_call = auth_message["player_id"]

            if player_id_making_call == player1_id:
                my_player_orm = player1_orm
                is_player1_in_game = True
            elif player_id_making_call == player2_id:
                my_player_orm = player2_orm
                is_player1_in_game = False
            else:
                await websocket.close(code=1008, reason="Произошла ошибка")
                return

            # обновляю статус игрока на "играет"
            if my_player_orm and my_player_orm.status == 0:
                 my_player_orm.status = 1
                 await db.commit()
                 await db.refresh(my_player_orm)

            # отправляю начальное состояние игры
            game_state = {
                "type": "game_start",
                "game_id": game.id,
                "player1_id": player1_id,
                "player2_id": player2_id,
                "player1_login": player1_orm.login,
                "player2_login": player2_orm.login,
                "my_id": player_id_making_call,
                "your_board": json.loads(game.board_player_1) if is_player1_in_game else json.loads(game.board_player_2),
                "opponent_board": json.loads(game.board_player_2) if is_player1_in_game else json.loads(game.board_player_1),
                "p1_res": game.p_1_res,
                "p2_res": game.p_2_res,
                "turn": game.current_turn_player_id
            }
            await websocket.send_json(game_state)

            # оповещаю игрока о подключении другого участника
            await manager.broadcast_to_all_in_game(
                json.dumps({
                    "type": "player_connected",
                    "player_id": player_id_making_call,
                    "login": my_player_orm.login if my_player_orm else "Unknown"
                }),
                game_id
            )

        else:
            await websocket.close(code=1008, reason="Произошла ошибка, необходима аунтефикация")
            return

        # основной цикл обработки сообщений
        while True:
            data = await websocket.receive_json()
            message_type = data.get("type")

            if message_type == "move":
                target_row = data.get("row")
                target_col = data.get("col")

                if target_row is None or target_col is None:
                    await websocket.send_json({"type": "error", "message": "Необходимо указать row и col (строка и столбец)"})
                    continue

                # обрабатываю ход
                message, my_board_json_updated, opponent_board_json_updated = await GameService.process_player_move(
                    db, game_id, player_id_making_call, target_row, target_col
                )

                if my_board_json_updated is None:
                    await websocket.send_json({"type": "error", "message": message})
                    continue

                # обновляю состояние игры после хода
                game = await GameService.get_game_by_id(db, game_id)

                current_player_moved_id = player_id_making_call

                # определяю, чей ход будет следующим
                next_turn_player_id = None
                if game.player_1_id == current_player_moved_id:
                    game.current_turn_player_id = game.player_2_id
                else:
                    game.current_turn_player_id = game.player_1_id

                updated_state_message = {
                    "type": "move_result",
                    "message": message,
                    "player_who_moved": current_player_moved_id,
                    "your_board": json.loads(my_board_json_updated),
                    "opponent_board": json.loads(opponent_board_json_updated),
                    "p1_res": game.p_1_res,
                    "p2_res": game.p_2_res,
                    "is_game_over": not game.online,
                    "winner_id": game.player_1_id if game.p_1_res == 1 else (
                        game.player_2_id if game.p_2_res == 1 else None),
                    "turn": game.current_turn_player_id if game.online else None
                }

                await manager.broadcast_to_all_in_game(json.dumps(updated_state_message), game_id)

                # если игра завершилась, обновляю статусы игроков и выставляю игру как неактивную
                if not game.online:
                    await PlayerService.update_player_stats(db, game, game.player_1_id)
                    await PlayerService.update_player_stats(db, game, game.player_2_id)

                    await PlayerService.logout_player(db, game.player_1_id)
                    await PlayerService.logout_player(db, game.player_2_id)

                    await manager.broadcast_to_all_in_game(
                        json.dumps({"type": "game_over", "winner_id": updated_state_message["winner_id"]}),
                        game_id
                    )
                    for conn in manager.active_connections.get(game_id, []):
                        await conn.close(code=1000, reason="Игра завершена")
                    if game_id in manager.active_connections:
                        del manager.active_connections[game_id]


            elif message_type == "chat":
                chat_message_content = data.get("content")
                if chat_message_content:
                    await manager.broadcast(
                        json.dumps({
                            "type": "chat_message",
                            "sender_id": player_id_making_call,
                            "sender_login": my_player_orm.login if my_player_orm else "Unknown",
                            "content": chat_message_content
                        }),
                        game_id,
                        sender_websocket=websocket
                    )

    except WebSocketDisconnect:
        # игрок отключился
        manager.disconnect(websocket, game_id)

        if game and game.online:
            winner_id = None
            # определяю, кто победил, в случае отключения одного из игрока
            # если вышел игрок 1, то победил игрок 2 и наоборот
            if player_id_making_call == game.player_1_id:
                game.p_2_res = 1
                winner_id = game.player_2_id
            elif player_id_making_call == game.player_2_id:
                game.p_1_res = 1
                winner_id = game.player_1_id

            if winner_id:
                game.online = False
                await db.commit()
                await db.refresh(game)

                # обновляю статистику
                await PlayerService.update_player_stats(db, game, player1_id)
                await PlayerService.update_player_stats(db, game, player2_id)

                # отправляю сообщение для оставшегося игрока об отключении опонента
                await manager.broadcast_to_all_in_game(
                    json.dumps({"type": "opponent_disconnected", "winner_id": winner_id}),
                    game_id
                )
                # завершаю игру
                for conn in manager.active_connections.get(game_id, []):
                     await conn.close(code=1000, reason="Игрок отключился")
                if game_id in manager.active_connections:
                    del manager.active_connections[game_id]

    except Exception as e:
        print(f"Ошибка вебсокета во время игры: {game_id}: {e}")
        await websocket.close(code=1011, reason="Error")
        manager.disconnect(websocket, game_id)
        # если произошла крит ошибка во время игры, то я ее отключаю
        if game and game.online:
            try:
                # если игрок 1 отправил запрос из-за которой произошла крит ошибка, то игрок 2 побеждает
                winner_id = None
                if player_id_making_call == game.player_1_id:
                    game.p_2_res = 1
                    winner_id = game.player_2_id
                else:
                    game.p_1_res = 1
                    winner_id = game.player_1_id

                game.online = False
                await db.commit()
                await db.refresh(game)
                await PlayerService.update_player_stats(db, game, player1_id)
                await PlayerService.update_player_stats(db, game, player2_id)

                await manager.broadcast_to_all_in_game(
                    json.dumps({"type": "server_error_game_over", "winner_id": winner_id}),
                    game_id
                )
            except Exception as close_err:
                print(f"Произошла ошибка во время игры: {close_err}")
