from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


def make_engine(url: str):
    if url.startswith("sqlite") and ":memory:" not in url:
        path = url.removeprefix("sqlite:///")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        url,
        connect_args={"check_same_thread": False, "timeout": 30} if url.startswith("sqlite") else {},
        pool_pre_ping=True,
    )
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def sqlite_pragmas(conn, _):
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA journal_mode=WAL")
            # Bounded 64 MiB per connection avoids spilling every medium-sized batch.
            # Keep SQLite's FULL synchronization: checkpoints must survive a restart.
            conn.execute("PRAGMA cache_size=-65536")
            # Amortize random index writes: ~128 MiB at SQLite's default 4 KiB page size.
            # FULL still syncs every committed WAL transaction; checkpoint timing is independent.
            conn.execute("PRAGMA wal_autocheckpoint=32768")

    return engine


engine = make_engine(settings.database_url)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def get_db():
    with SessionLocal() as session:
        yield session
