"""Policy route: the active policy version, rules and source text."""

from fastapi import APIRouter

from kangaroo.api.schemas import PolicyView
from kangaroo.api.services import ServicesDep

router = APIRouter(tags=["policy"])


@router.get("/policy")
async def policy(svc: ServicesDep) -> PolicyView:
    return PolicyView(
        version=svc.policy.version,
        rules=list(svc.policy.rules.values()),
        markdown=svc.policy.text,
    )
