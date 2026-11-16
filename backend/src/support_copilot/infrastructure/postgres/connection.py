"""Each operation owns one connection/transaction; no shared thread connections."""

from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row


class Database:
    def __init__(self, dsn: str):
        self.dsn = dsn

    @contextmanager
    def transaction(self):
        with psycopg.connect(
            self.dsn,
            row_factory=dict_row,
            connect_timeout=10,
            options="-c statement_timeout=15000 -c lock_timeout=5000",
        ) as conn:
            yield conn
