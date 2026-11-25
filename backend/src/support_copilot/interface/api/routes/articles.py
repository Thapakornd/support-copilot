from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query

from support_copilot.application.errors import NotFound
from support_copilot.interface.api.deps import ArticleReader, SignedIn
from support_copilot.interface.api.types import ApiModel, text

router = APIRouter()


class ArticleBody(ApiModel):
    steps: list[str]
    note: str | None = None


class Article(ApiModel):
    id: str
    title: str
    type: str
    product: str
    topic: str
    updated: datetime
    excerpt: str


class ArticleDetail(Article):
    content: str
    source_url: str
    body: ArticleBody | None = None


@router.get("/articles", response_model_exclude_none=True)
def list_articles(_: SignedIn, articles: ArticleReader) -> list[Article]:
    return [Article(**a) for a in articles.list()]


# Declared before /articles/{article_id} so "search" is never read as an id.
@router.get("/articles/search", response_model_exclude_none=True)
def search_articles(
    _: SignedIn,
    articles: ArticleReader,
    q: Annotated[text(4000), Query()] = "",
    topic: Annotated[text(200) | None, Query()] = None,
) -> list[Article]:
    found = articles.search(q, topic) if q else articles.list(topic)
    return [Article(**a) for a in found]


@router.get("/articles/{article_id}", response_model_exclude_none=True)
def get_article(article_id: str, _: SignedIn, articles: ArticleReader) -> ArticleDetail:
    article = None if "\x00" in article_id else articles.get(article_id)
    if article is None:
        raise NotFound
    return ArticleDetail(**article)
