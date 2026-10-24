"""Bounded, metric RoomPlan interchange data.

The capture is an immutable observation reported by the authenticated client.
RoomPlan confidence is not an accuracy guarantee; user measurements are a
separate overlay and never overwrite dimensions in the original capture.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import (
    AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator,
)

MAX_CAPTURE_BYTES = 2 * 1024 * 1024
MAX_PATCH_BYTES = 256 * 1024
MAX_ROOMS = 50
MAX_ELEMENTS = 2000
MAX_DIMENSION_M = 100.0
MAX_COORDINATE_M = 1000.0

Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")]
Name = Annotated[str, Field(min_length=1, max_length=80)]
Number = Annotated[float, Field(strict=True, allow_inf_nan=False)]
Confidence = Literal["high", "medium", "low", "unknown"]


def clean_name(value: str) -> str:
    value = value.strip()
    if not value or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError("Inserisci un nome leggibile, senza caratteri di controllo.")
    return value


class CaptureModel(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True, allow_inf_nan=False)


class Dimensions(CaptureModel):
    x: Number = Field(ge=0, le=MAX_DIMENSION_M)
    y: Number = Field(ge=0, le=MAX_DIMENSION_M)
    z: Number = Field(ge=0, le=MAX_DIMENSION_M)


class Point(CaptureModel):
    x: Number = Field(ge=-MAX_COORDINATE_M, le=MAX_COORDINATE_M)
    y: Number = Field(ge=-MAX_COORDINATE_M, le=MAX_COORDINATE_M)
    z: Number = Field(ge=-MAX_COORDINATE_M, le=MAX_COORDINATE_M)


class Geometry(CaptureModel):
    id: Identifier
    dimensions: Dimensions
    transform: list[Number] = Field(min_length=16, max_length=16)
    confidence: Confidence = "unknown"

    @field_validator("transform")
    @classmethod
    def rigid_transform(cls, matrix: list[float]) -> list[float]:
        """Apple matrices are column-major rigid transforms, with metres at 12..14."""
        if any(abs(v) > MAX_COORDINATE_M for v in matrix):
            raise ValueError("Coordinate della scansione fuori dall'intervallo supportato.")
        if any(abs(matrix[i]) > 0.001 for i in (3, 7, 11)) or abs(matrix[15] - 1) > 0.001:
            raise ValueError("La matrice deve essere una trasformazione affine 4×4 valida.")
        axes = [matrix[start:start + 3] for start in (0, 4, 8)]
        for axis in axes:
            if abs(sum(v * v for v in axis) - 1) > 0.02:
                raise ValueError("La trasformazione non può alterare la scala delle misure.")
        for a, b in ((0, 1), (0, 2), (1, 2)):
            if abs(sum(x * y for x, y in zip(axes[a], axes[b]))) > 0.02:
                raise ValueError("Gli assi della trasformazione devono essere ortogonali.")
        a, b, c = axes
        determinant = (a[0] * (b[1] * c[2] - b[2] * c[1])
                       - b[0] * (a[1] * c[2] - a[2] * c[1])
                       + c[0] * (a[1] * b[2] - a[2] * b[1]))
        if not math.isclose(determinant, 1.0, abs_tol=0.03):
            raise ValueError("L'orientamento della trasformazione non è valido.")
        return matrix


class Surface(Geometry):
    polygon_corners: list[Point] | None = Field(default=None, min_length=3, max_length=64)

    @model_validator(mode="after")
    def nonzero_surface(self):
        if sum(value > 0 for value in self.dimensions.model_dump().values()) < 2:
            raise ValueError("Una superficie deve avere almeno due dimensioni positive.")
        return self


class CapturedObject(Geometry):
    category: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z][A-Za-z0-9_ -]*$")

    @model_validator(mode="after")
    def nonzero_object(self):
        if any(value <= 0 for value in self.dimensions.model_dump().values()):
            raise ValueError("Le dimensioni di un oggetto devono essere positive.")
        return self


class CapturedRoom(CaptureModel):
    id: Identifier
    name: Name = "Stanza"
    walls: list[Surface] = Field(min_length=1, max_length=100)
    doors: list[Surface] = Field(default_factory=list, max_length=100)
    windows: list[Surface] = Field(default_factory=list, max_length=100)
    openings: list[Surface] = Field(default_factory=list, max_length=100)
    floors: list[Surface] = Field(default_factory=list, max_length=20)
    objects: list[CapturedObject] = Field(default_factory=list, max_length=200)

    _name = field_validator("name")(clean_name)

    @model_validator(mode="after")
    def unique_geometry(self):
        ids = []
        for group in (self.walls, self.doors, self.windows, self.openings, self.floors, self.objects):
            ids.extend(item.id for item in group)
        if len(ids) != len(set(ids)):
            raise ValueError("Ogni elemento della stanza deve avere un identificativo distinto.")
        for wall in self.walls:
            if wall.dimensions.x <= 0 or wall.dimensions.y <= 0:
                raise ValueError("Lunghezza e altezza delle pareti devono essere positive.")
        return self


class HouseCapture(CaptureModel):
    schema_version: Literal[1]
    capture_id: Identifier
    # "manual": rooms the person measured and typed in, built by the server.
    source: Literal["apple_roomplan", "manual"]
    captured_at: AwareDatetime
    rooms: list[CapturedRoom] = Field(min_length=1, max_length=MAX_ROOMS)

    @field_validator("schema_version", mode="before")
    @classmethod
    def integer_version(cls, value):
        if type(value) is not int:
            raise ValueError("La versione dello schema deve essere un numero intero.")
        return value

    @field_validator("captured_at", mode="before")
    @classmethod
    def iso_timestamp(cls, value):
        if not isinstance(value, (str, datetime)):
            raise ValueError("Usa una data ISO 8601 con fuso orario.")
        if isinstance(value, str) and (len(value) > 40 or "T" not in value):
            raise ValueError("Usa una data ISO 8601 con fuso orario.")
        return value

    @field_validator("captured_at")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        try:
            return value.astimezone(timezone.utc)
        except (OverflowError, ValueError):
            raise ValueError("La data della scansione non rientra nell'intervallo supportato.") from None

    @model_validator(mode="after")
    def bounded_unique_rooms(self):
        room_ids = [room.id for room in self.rooms]
        if len(room_ids) != len(set(room_ids)):
            raise ValueError("Le stanze devono avere identificativi distinti.")
        elements = sum(len(getattr(room, group)) for room in self.rooms
                       for group in ("walls", "doors", "windows", "openings", "floors", "objects"))
        if elements > MAX_ELEMENTS:
            raise ValueError("La scansione supera il limite di 2000 elementi.")
        return self


class CreateHouseScan(CaptureModel):
    title: Name = "Casa"
    capture: HouseCapture

    _title = field_validator("title")(clean_name)


class RoomLabel(CaptureModel):
    room_id: Identifier
    name: Name

    _name = field_validator("name")(clean_name)


class WallMeasurement(CaptureModel):
    room_id: Identifier
    wall_id: Identifier
    # A null length explicitly removes the user's verification.
    length_m: Number | None = Field(gt=0, le=MAX_DIMENSION_M)


class UpdateHouseScan(CaptureModel):
    revision: int = Field(strict=True, ge=1, le=2_147_483_647)
    title: Name | None = None
    room_labels: list[RoomLabel] = Field(default_factory=list, max_length=MAX_ROOMS)
    wall_measurements: list[WallMeasurement] = Field(default_factory=list, max_length=MAX_ELEMENTS)

    @field_validator("title")
    @classmethod
    def readable_title(cls, value):
        if value is None:
            raise ValueError("Il titolo non può essere nullo.")
        return clean_name(value)

    @model_validator(mode="after")
    def unique_updates(self):
        if self.title is None and not self.room_labels and not self.wall_measurements:
            raise ValueError("Indica almeno un nome o una misura da aggiornare.")
        labels = [item.room_id for item in self.room_labels]
        measurements = [(item.room_id, item.wall_id) for item in self.wall_measurements]
        if len(labels) != len(set(labels)) or len(measurements) != len(set(measurements)):
            raise ValueError("Indica una sola modifica per ogni stanza o parete.")
        return self


class ManualRoom(CaptureModel):
    """A rectangular room measured by hand: what anyone without LiDAR can do."""
    name: Name
    length_m: Number = Field(ge=0.5, le=30)
    width_m: Number = Field(ge=0.5, le=30)
    height_m: Number = Field(default=2.7, ge=1.8, le=8)
    doors: int = Field(default=1, ge=0, le=4)
    windows: int = Field(default=1, ge=0, le=4)

    _name = field_validator("name")(clean_name)


class AddManualRoom(CaptureModel):
    room: ManualRoom
    # Absent: a new plan is started with this room. Present: the room joins it.
    scan_id: Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")] | None = None
    revision: int | None = Field(default=None, ge=1, le=2_147_483_647)
    title: Name = "Casa"

    _title = field_validator("title")(clean_name)

    @model_validator(mode="after")
    def revision_with_plan(self):
        if self.scan_id and self.revision is None:
            raise ValueError("Indica la revisione della pianta a cui aggiungere la stanza.")
        return self
