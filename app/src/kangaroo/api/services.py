"""The app's shared services, handed to route handlers through `ServicesDep`."""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request

from kangaroo.ai.agents.runner import RunService
from kangaroo.db.repository import Repository
from kangaroo.policy import Policy


@dataclass
class Services:
    repo: Repository
    runs: RunService
    policy: Policy


def get_services(request: Request) -> Services:
    return request.app.state.services


ServicesDep = Annotated[Services, Depends(get_services)]
