"""Provider readiness only. Operational PNP records never leave through this API."""

from fastapi import APIRouter, Depends

from ..geocoding_provider import provider_status
from ..models import User
from ..security import current_user

router = APIRouter()


@router.get("/api/geocoding-provider")
def geocoding_provider(_: User = Depends(current_user)):
    return provider_status()
