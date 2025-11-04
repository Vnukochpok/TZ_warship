from pydantic import BaseModel, Field, ConfigDict

class PlayerCreate(BaseModel):
    login: str = Field(..., min_length=3, max_length=20)
    password: str = Field(..., min_length=4, max_length=30)

class PlayerLogin(BaseModel):
    login: str
    password: str

class Player(BaseModel):
    id: int
    login: str
    stats: int
    status: int

    model_config = ConfigDict(from_attributes=True)

class PlayerStats(BaseModel):
    id: int
    login: str
    total_games: int = 0
    wins: int = 0
    losses: int = 0
