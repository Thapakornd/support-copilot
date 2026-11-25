from support_copilot.domain.articles import (
    clean_excerpt,
    display_body,
    product_label,
    source_type_label,
)
from support_copilot.infrastructure.postgres.connection import Database

_COLUMNS = """d.document_id, r.title, r.source_type, r.product, r.category_id,
       r.fetched_at, r.excerpt"""
_SERVABLE = """knowledge_documents d
JOIN knowledge_document_revisions r
  ON r.id = d.current_revision_id AND r.document_id = d.document_id
WHERE d.is_active"""
_TOPIC = " AND (%(topic)s::text IS NULL OR r.category_id = %(topic)s::text)"

# OR together the english lexemes of the query (users type whole sentences).
# Lexemes come from to_tsvector, so no query syntax typed by the user is parsed.
_ANY_WORD = """WITH RECURSIVE lex AS (
    SELECT lexeme, row_number() OVER (ORDER BY lexeme) AS n
    FROM unnest(to_tsvector('english', %(q)s))
), acc AS (
    SELECT n, plainto_tsquery('simple', lexeme) AS q FROM lex WHERE n = 1
    UNION ALL
    SELECT lex.n, acc.q || plainto_tsquery('simple', lex.lexeme)
    FROM acc JOIN lex ON lex.n = acc.n + 1
), query AS (SELECT q FROM acc ORDER BY n DESC LIMIT 1)"""


def _article(row: dict) -> dict:
    return {
        "id": row["document_id"],
        "title": row["title"],
        "type": source_type_label(row["source_type"]),
        "product": product_label(row["product"]),
        "topic": row["category_id"],
        "updated": row["fetched_at"],
        "excerpt": clean_excerpt(row["excerpt"]),
    }


class ArticleRepository:
    def __init__(self, db: Database):
        self.db = db

    def list(self, topic: str | None = None) -> list[dict]:
        with self.db.transaction(read_only=True) as conn:
            rows = conn.execute(
                f"SELECT {_COLUMNS} FROM {_SERVABLE}{_TOPIC}"
                " ORDER BY r.fetched_at DESC, d.document_id",
                {"topic": topic},
            ).fetchall()
        return [_article(row) for row in rows]

    def get(self, document_id: str) -> dict | None:
        with self.db.transaction(read_only=True) as conn:
            row = conn.execute(
                f"""SELECT {_COLUMNS}, r.content_markdown, r.source_url, r.display_body
                    FROM {_SERVABLE} AND d.document_id = %s""",
                (document_id,),
            ).fetchone()
        if row is None:
            return None
        return _article(row) | {
            "content": row["content_markdown"],
            "source_url": row["source_url"],
            "body": display_body(row["display_body"]),
        }

    def search(self, q: str, topic: str | None = None) -> list[dict]:
        # ponytail: ranks matches on the fly; add a stored weighted tsvector if the corpus grows large.
        with self.db.transaction(read_only=True) as conn:
            rows = conn.execute(
                f"""{_ANY_WORD}
                    SELECT {_COLUMNS} FROM query, {_SERVABLE}{_TOPIC}
                      AND to_tsvector('english', r.title || ' ' || r.excerpt || ' ' || r.content_markdown)
                          @@ query.q
                    ORDER BY ts_rank(
                        setweight(to_tsvector('english', r.title), 'A')
                        || setweight(to_tsvector('english', r.excerpt || ' ' || r.content_markdown), 'D'),
                        query.q, 1) DESC, d.document_id
                    LIMIT 50""",
                {"q": q, "topic": topic},
            ).fetchall()
        return [_article(row) for row in rows]
