"""List pets tool for querying pet hospital records."""

from __future__ import annotations

import logging
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

logger = logging.getLogger(__name__)

# Allowed values from the Go API /api/v1/meta
SPECIES_VALUES = ["犬", "猫", "兔", "鸟", "仓鼠", "爬宠", "其他"]
STATUS_VALUES = ["待就诊", "就诊中", "住院中", "已康复", "慢性病随访"]
SORT_BY_VALUES = [
    "id", "name", "ownerName", "species", "doctor", "disease",
    "status", "totalCost", "visitCount", "createdAt", "updatedAt"
]
ORDER_VALUES = ["asc", "desc"]


# --- Input Model ---

class ListPetsInput(BaseModel):
    """Input parameters for the list_pets tool.

    Maps 1:1 to the Go REST API GET /api/v1/pets query parameters.
    """

    model_config = {"extra": "forbid"}  # Reject unknown fields

    q: str | None = Field(None, description="Full-text search across all fields")
    name: str | None = Field(None, description="Filter by pet name (partial match)")
    ownerName: str | None = Field(None, description="Filter by owner name (partial match)")
    ownerPhone: str | None = Field(None, description="Filter by owner phone (partial match)")
    species: Literal["犬", "猫", "兔", "鸟", "仓鼠", "爬宠", "其他"] | None = Field(
        None, description="Filter by species"
    )
    doctor: str | None = Field(None, description="Filter by attending doctor")
    disease: str | None = Field(None, description="Filter by disease/diagnosis")
    status: Literal["待就诊", "就诊中", "住院中", "已康复", "慢性病随访"] | None = Field(
        None, description="Filter by visit status"
    )
    min: float | None = Field(None, ge=0, description="Minimum total cost filter")
    max: float | None = Field(None, ge=0, description="Maximum total cost filter")
    sortBy: Literal[
        "id", "name", "ownerName", "species", "doctor", "disease",
        "status", "totalCost", "visitCount", "createdAt", "updatedAt"
    ] | None = Field(None, description="Field to sort by")
    order: Literal["asc", "desc"] | None = Field(None, description="Sort order")
    page: int = Field(1, ge=1, description="Page number (1-based)")
    pageSize: int = Field(20, ge=1, le=500, description="Items per page (max 500)")

    @model_validator(mode="after")
    def validate_min_max(self) -> "ListPetsInput":
        """Ensure min <= max when both are provided."""
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError(f"min ({self.min}) must be <= max ({self.max})")
        return self


# --- Output Models ---

class Record(BaseModel):
    """A medical record entry."""

    id: str | None = None
    visitDate: str | None = None
    doctor: str | None = None
    diagnosis: str | None = None
    symptoms: str | None = None
    treatment: str | None = None
    prescription: list[str] | None = None
    weightKg: float | None = None
    temperature: float | None = None
    followUp: str | None = None
    charge: float | None = None
    createdAt: str | None = None


class Charge(BaseModel):
    """A charge/fee entry."""

    id: str | None = None
    item: str | None = None
    category: str | None = None
    amount: float | None = None
    doctor: str | None = None
    date: str | None = None


class Pet(BaseModel):
    """A pet record from the hospital."""

    id: str
    name: str
    species: str
    breed: str | None = None
    gender: str | None = None
    ageMonths: int | None = None
    color: str | None = None
    chipNo: str | None = None
    ownerName: str
    ownerPhone: str
    ownerAddr: str | None = None
    doctor: str
    disease: str
    status: str
    allergy: str | None = None
    note: str | None = None
    records: list[Record] | None = None
    charges: list[Charge] | None = None
    totalCost: float = 0.0
    visitCount: int = 0
    createdAt: str | None = None
    updatedAt: str | None = None


class ListPetsOutput(BaseModel):
    """Output from the list_pets tool.

    Maps to the Go API success response 'data' field.
    """

    items: list[Pet]
    total: int
    page: int
    pageSize: int
    totalPages: int
    totalCost: float


class ErrorOutput(BaseModel):
    """Error output structure."""

    error: dict[str, Any]


# --- Tool function ---

async def list_pets(
    rest_client: Any,  # PetHospitalClient, avoiding circular import
    **kwargs: Any,
) -> dict[str, Any]:
    """List and search pets in the hospital database.

    Queries the pet hospital backend to retrieve pet records with optional
    filtering, sorting, and pagination. Supports full-text search and
    field-specific filters.

    Use cases:
    - Search for pets by name, owner, disease, or doctor
    - Filter by species (犬/猫/兔/鸟/仓鼠/爬宠/其他)
    - Filter by visit status (待就诊/就诊中/住院中/已康复/慢性病随访)
    - Filter by total cost range
    - Sort results by any field
    - Paginate through large result sets

    Returns pet records including medical history and charges.
    """
    from ..logging_config import LogContext

    # Validate input
    try:
        input_data = ListPetsInput(**kwargs)
    except Exception as e:
        from ..errors import ValidationError
        raise ValidationError(f"Invalid input parameters: {e}")

    # Build query parameters (only include non-None values)
    params: dict[str, Any] = {}
    if input_data.q is not None:
        params["q"] = input_data.q
    if input_data.name is not None:
        params["name"] = input_data.name
    if input_data.ownerName is not None:
        params["ownerName"] = input_data.ownerName
    if input_data.ownerPhone is not None:
        params["ownerPhone"] = input_data.ownerPhone
    if input_data.species is not None:
        params["species"] = input_data.species
    if input_data.doctor is not None:
        params["doctor"] = input_data.doctor
    if input_data.disease is not None:
        params["disease"] = input_data.disease
    if input_data.status is not None:
        params["status"] = input_data.status
    if input_data.min is not None:
        params["min"] = input_data.min
    if input_data.max is not None:
        params["max"] = input_data.max
    if input_data.sortBy is not None:
        params["sortBy"] = input_data.sortBy
    if input_data.order is not None:
        params["order"] = input_data.order
    params["page"] = input_data.page
    params["pageSize"] = input_data.pageSize

    with LogContext(logger, "list_pets", params):
        # Call backend
        data = await rest_client.get_pets(params)

        # Parse and validate response
        try:
            output = ListPetsOutput(**data)
            return output.model_dump()
        except Exception as e:
            from ..errors import BackendInvalidResponseError
            raise BackendInvalidResponseError(f"Invalid response data from backend: {e}")
