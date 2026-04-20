from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=12)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    email: str
    display_name: str


class PasswordResetRequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr


class PasswordResetCompleteBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str
    new_password: str = Field(min_length=12)
