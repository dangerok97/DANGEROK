"""Owner-declared identity, shared by registration and telephone introductions."""
from datetime import datetime, timezone
import unicodedata

from pydantic import BaseModel, Field, field_validator, model_validator


class IdentityIn(BaseModel):
    first_name: str = Field(min_length=1, max_length=60)
    last_name: str = Field(min_length=1, max_length=60)
    tutorial_seen: bool = False

    @field_validator("first_name", "last_name")
    @classmethod
    def person_name(cls, value: str) -> str:
        value = " ".join(unicodedata.normalize("NFC", value).split())
        if not value or not any(c.isalpha() for c in value) or any(
            not (c.isalpha() or unicodedata.category(c).startswith("M") or c in " '-’.·")
            for c in value
        ):
            raise ValueError("Inserisci un nome o cognome valido")
        return value

    @model_validator(mode="after")
    def full_name_length(self):
        if len(f"{self.first_name} {self.last_name}") > 80:
            raise ValueError("Nome e cognome possono contenere al massimo 80 caratteri")
        return self

    def updates(self) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        result = {"first_name": self.first_name, "last_name": self.last_name,
                  "name": f"{self.first_name} {self.last_name}", "identity_confirmed_at": now}
        if self.tutorial_seen:
            result.update(knowledge_tutorial_version=1, knowledge_tutorial_seen_at=now)
        return result


def owner_full_name(user: dict) -> str:
    first, last = user.get("first_name"), user.get("last_name")
    if first and last:
        return f"{first} {last}".strip()
    # Existing accounts keep their declared display name; never invent a surname.
    return str(user.get("name") or first or "").strip()
