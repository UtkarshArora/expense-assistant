from fastapi import APIRouter, Depends

from ..auth import get_current_user
from ..models import User
from ..schemas import MeOut

router = APIRouter()


@router.get("/me", response_model=MeOut)
async def me(user: User = Depends(get_current_user)) -> MeOut:
    return MeOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        department=user.department,
        employee_name=user.employee_name,
    )
