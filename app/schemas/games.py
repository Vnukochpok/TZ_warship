from pydantic import BaseModel, ConfigDict
from datetime import datetime

class GameCreate(BaseModel):
    player_1_id: int
    player_2_id: int

class Game(BaseModel):
    id: int
    player_1_id: int
    player_2_id: int
    p_1_res: int
    p_2_res: int
    online: bool
    start_date: datetime
    board_player_1: str
    board_player_2: str

    model_config = ConfigDict(from_attributes=True)

class GameWithPlayerLogins(BaseModel):
    id: int
    player_1_login: str
    player_2_login: str
    p_1_res: int
    p_2_res: int
    online: bool
    start_date: datetime