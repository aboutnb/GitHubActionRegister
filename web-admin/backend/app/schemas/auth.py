from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token_type: str = "bearer"
    username: str
    role: str


class CurrentUserResponse(BaseModel):
    username: str
    role: str
