from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LoginInput(Input):
    username: str = Field(min_length=1, max_length=100)
    password: Annotated[str, StringConstraints(strip_whitespace=False)] = Field(min_length=1, max_length=1024)


class UploadInput(Input):
    filename: str = Field(min_length=1, max_length=255)
    size: int = Field(gt=0)


class RunInput(Input):
    upload_id: str
    name: str = Field(min_length=1, max_length=200)
    sheet: str | None = Field(default=None, max_length=150)
    mapping: dict[str, str] | None = None
    delimiter: Literal[",", ";", "\t", "|"] = ","
    encoding: Literal["utf-8-sig", "utf-8", "cp1252", "latin-1"] = "utf-8-sig"
    reference_id: str | None = None
    crs: Literal["EPSG:4326"] | None = None


class ReprocessInput(Input):
    reference_id: str | None = None


class DecisionInput(Input):
    expected_revision: int = Field(ge=1)
    action: Literal["accept_candidate", "manual_point", "address_only", "unresolved", "reopen"]
    candidate_id: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False)
    longitude: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)
    precision: (
        Literal["PUERTA", "INTERSECCION", "SITIO", "CUADRA", "NUCLEO", "VIA", "COORDENADA", "DESCONOCIDA"]
        | None
    ) = None
    address: str | None = Field(default=None, max_length=3000)
    reason: str = Field(min_length=8, max_length=3000)
    evidence: str | None = Field(default=None, max_length=3000)


class ExportInput(Input):
    profile: Literal["locations", "source_rows"] = "locations"
    safe_spreadsheet: bool = True
