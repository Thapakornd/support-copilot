from typing import Annotated

from fastapi import APIRouter
from pydantic import StrictBool, StringConstraints

from support_copilot.application.errors import Forbidden
from support_copilot.interface.api.deps import (
    Accounts,
    AgentUser,
    CustomerUser,
    SignedIn,
)
from support_copilot.interface.api.types import ApiModel, text

router = APIRouter()


class Me(ApiModel):
    name: str
    email: str
    company: str
    role: str


class TeamMember(ApiModel):
    name: str
    email: str
    role: str
    cases: bool


class Notify(ApiModel):
    replies: StrictBool
    status: StrictBool
    digest: StrictBool


class ProfileOut(ApiModel):
    """Stored values may predate the input limits, so no constraints here."""

    name: str
    email: str
    company: str
    timezone: str
    phone: str
    notify: Notify


class Profile(ApiModel):
    name: text(200, 1)
    email: Annotated[text(320), StringConstraints(pattern=r"^[^@\s]+@[^@\s]+$")]
    company: text(200)
    timezone: text(64, 1)
    phone: text(50)
    notify: Notify


@router.get("/me", response_model_exclude_none=True)
def me(user: SignedIn) -> Me:
    return Me(name=user.name, email=user.email, company=user.company, role=user.role)


@router.get("/agents")
def agents(_: AgentUser, accounts: Accounts) -> list[str]:
    return accounts.list_agents()


@router.get("/team", response_model_exclude_none=True)
def team(user: CustomerUser, accounts: Accounts) -> list[TeamMember]:
    if user.account_id is None:
        raise Forbidden
    return [TeamMember(**member) for member in accounts.list_team(user.account_id)]


@router.get("/profile")
def get_profile(user: SignedIn, accounts: Accounts) -> ProfileOut:
    return ProfileOut(**accounts.get_profile(user))


@router.put("/profile")
def put_profile(profile: Profile, user: SignedIn, accounts: Accounts) -> ProfileOut:
    n = profile.notify
    saved = accounts.save_profile(
        user.id,
        {**profile.model_dump(exclude={"notify"}), **n.model_dump()},
    )
    return ProfileOut(**saved)
