"""Request-scoped dependencies shared by every authenticated route.

Declare the user dependency before any repository dependency so that 401 wins
over 503. Real authentication replaces `current_user` only.
"""

from typing import Annotated

from fastapi import Depends, Header

from support_copilot.application.errors import Forbidden, Unauthorized
from support_copilot.bootstrap import (
    build_accounts,
    build_articles,
    build_database,
    build_tickets,
)
from support_copilot.core.config import settings
from support_copilot.domain.entities import CurrentUser
from support_copilot.infrastructure.postgres.accounts import AccountRepository
from support_copilot.infrastructure.postgres.articles import ArticleRepository
from support_copilot.infrastructure.postgres.connection import Database
from support_copilot.infrastructure.postgres.tickets import TicketRepository


def current_user(x_demo_user: Annotated[str | None, Header()] = None) -> CurrentUser:
    if (
        not settings.demo_auth
        or not x_demo_user
        or not x_demo_user.strip()
        or "\x00" in x_demo_user
    ):
        raise Unauthorized
    user = build_accounts().find_demo_user(x_demo_user)
    if user is None:
        raise Unauthorized
    return user


def require_agent(user: Annotated[CurrentUser, Depends(current_user)]) -> CurrentUser:
    if user.role != "agent":
        raise Forbidden
    return user


def require_customer(
    user: Annotated[CurrentUser, Depends(current_user)],
) -> CurrentUser:
    if user.role != "customer":
        raise Forbidden
    return user


SignedIn = Annotated[CurrentUser, Depends(current_user)]
AgentUser = Annotated[CurrentUser, Depends(require_agent)]
CustomerUser = Annotated[CurrentUser, Depends(require_customer)]
Db = Annotated[Database, Depends(build_database)]
Accounts = Annotated[AccountRepository, Depends(build_accounts)]
ArticleReader = Annotated[ArticleRepository, Depends(build_articles)]
Tickets = Annotated[TicketRepository, Depends(build_tickets)]
