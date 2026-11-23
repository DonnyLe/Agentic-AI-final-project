"""Case routes: list, read and create meeting cases."""

from fastapi import APIRouter, HTTPException, status

from kangaroo.api.schemas import NewCase
from kangaroo.api.services import ServicesDep
from kangaroo.db.records import CaseSummary, StoredCase
from kangaroo.models.case import Case

router = APIRouter(tags=["cases"])


@router.get("/cases")
async def list_cases(svc: ServicesDep) -> list[CaseSummary]:
    return await svc.repo.list_cases()


@router.get("/cases/{case_id}")
async def get_case(case_id: str, svc: ServicesDep) -> StoredCase:
    stored = await svc.repo.get_case(case_id)

    if stored is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No case {case_id}.")

    return stored


@router.post("/cases", status_code=status.HTTP_201_CREATED)
async def create_case(body: NewCase, svc: ServicesDep) -> StoredCase:
    case = Case(id=await svc.repo.next_custom_case_id(), content=body.content)
    await svc.repo.upsert_cases([case], source="custom")

    return StoredCase(case=case, source="custom", golden=None)
