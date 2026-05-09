from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token_type: str = "bearer"
    username: str
    role: str
    must_change_password: bool = False


class CurrentUserResponse(BaseModel):
    username: str
    role: str
    must_change_password: bool = False


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
