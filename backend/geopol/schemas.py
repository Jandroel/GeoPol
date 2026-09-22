from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


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
    reference_id: str | None = Field(default=None, min_length=1, max_length=36)
    crs: Literal["EPSG:4326"] | None = None
    crs_evidence: str | None = Field(default=None, min_length=8, max_length=500)

    @model_validator(mode="after")
    def require_documented_crs(self):
        if self.crs is not None and not self.crs_evidence:
            raise ValueError("Indique la fuente que confirma el sistema de coordenadas EPSG:4326")
        if self.crs is None and self.crs_evidence is not None:
            raise ValueError("La evidencia del sistema de coordenadas requiere seleccionar EPSG:4326")
        return self


class ReprocessInput(Input):
    reference_id: str | None = Field(default=None, min_length=1, max_length=36)
    crs: Literal["EPSG:4326"] | None = None
    crs_evidence: str | None = Field(default=None, min_length=8, max_length=500)

    @model_validator(mode="after")
    def require_explicit_crs_confirmation(self):
        if "crs_evidence" in self.model_fields_set and "crs" not in self.model_fields_set:
            raise ValueError("Envíe el sistema de coordenadas junto con su fuente de confirmación")
        if self.crs is not None and not self.crs_evidence:
            raise ValueError("Indique la fuente que confirma el sistema de coordenadas EPSG:4326")
        if self.crs_evidence is not None and self.crs is None:
            raise ValueError("Envíe EPSG:4326 junto con su fuente de confirmación")
        return self


class ProcessingDefaultsInput(Input):
    reference_id: str | None = Field(min_length=1, max_length=36)


class DecisionInput(Input):
    expected_revision: int = Field(ge=1)
    action: Literal["accept_candidate", "manual_point", "address_only", "unresolved", "reopen"]
    candidate_id: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False)
    longitude: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)
    precision: (
        Literal[
            "PUERTA",
            "INTERSECCION",
            "SITIO",
            "CUADRA",
            "MANZANA",
            "NUCLEO",
            "VIA",
            "COORDENADA",
            "DESCONOCIDA",
        ]
        | None
    ) = None
    address: str | None = Field(default=None, max_length=3000)
    reason: str = Field(min_length=8, max_length=3000)
    evidence: str | None = Field(default=None, max_length=3000)
    learn_address: bool = False


class ExportInput(Input):
    profile: Literal["locations", "source_rows"] = "locations"
    safe_spreadsheet: bool = True


class MemoryRevokeInput(Input):
    reason: str = Field(min_length=8, max_length=3000)
