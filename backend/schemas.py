"""Validated request models for the HTTP API."""

import re
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator


def validate_email(value: str) -> str:
    value = value.strip().lower()
    if len(value) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
        raise ValueError("Введите корректный адрес электронной почты")
    return value


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: Annotated[str, Field(min_length=3, max_length=254)]
    password: Annotated[str, Field(min_length=8, max_length=128)]

    _normalize_email = field_validator("email")(validate_email)


class Registration(Credentials):
    name: Annotated[str | None, Field(default=None, min_length=2, max_length=80)] = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if len(value) < 2:
            raise ValueError("Имя должно содержать не менее 2 символов")
        return value


class CartUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quantity: Annotated[int, Field(ge=1, le=999, strict=True)]


class ContactMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=2, max_length=80)]
    email: Annotated[str, Field(min_length=3, max_length=254)]
    message: Annotated[str, Field(min_length=10, max_length=2000)]

    _normalize_email = field_validator("email")(validate_email)

    @field_validator("name", "message")
    @classmethod
    def trim_text(cls, value: str, info: ValidationInfo) -> str:
        value = value.strip()
        minimum_length = 2 if info.field_name == "name" else 10
        if len(value) < minimum_length:
            raise ValueError(f"Поле должно содержать не менее {minimum_length} символов")
        return value
