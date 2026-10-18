from collections.abc import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

settings = get_settings()

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_async_engine(settings.database_url, echo=False, connect_args=connect_args)

if settings.database_url.startswith("sqlite"):
    # SQLite does not enforce foreign keys unless told to per-connection
    # — without this, every ON DELETE CASCADE/SET NULL in this app's
    # models (see app/services/account_deletion.py for why those matter)
    # would silently no-op against SQLite while still being correctly
    # enforced against real Postgres, exactly the kind of divergence
    # this project has been bitten by before (see docs/CHECKLIST.md's
    # "verify the test suite against real Postgres" round).
    @event.listens_for(engine.sync_engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """For code that needs to open its own session outside the
    request/response cycle — a FastAPI BackgroundTasks callback, whose
    request-scoped `db` (from get_db above) is already closed by the
    time it runs. A plain module-level import of AsyncSessionLocal
    would work in production but silently break under the test suite,
    which overrides get_db with a session bound to a different
    (in-memory, per-test) engine — going through this dependency
    instead lets tests override it the same way, so a background task's
    writes land in the same database the test actually asserts
    against."""
    return AsyncSessionLocal
