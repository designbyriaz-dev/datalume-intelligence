import tempfile
from collections.abc import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# Must run before anything else imports app.core.config — app.main does,
# at module level (`settings = get_settings()`), so this has to happen
# before the `from app.main import app` below, which is the first thing
# in this file that would otherwise trigger it. Every integration this
# test suite exercises against a *fake* edge (Stripe, the LLM client,
# SMTP, OIDC) expects to start from "not configured" by default and has
# each test opt into specific values via monkeypatch/os.environ +
# get_settings.cache_clear() (see test_billing.py, test_sso.py,
# test_auth_email_flows.py). That assumption silently broke once real
# credentials for those integrations were added to a developer's own
# apps/api/.env (verified against real accounts — see
# docs/CHECKLIST.md): every test run started picking them up, so e.g.
# registering a user in an unrelated test would try a real SMTP
# connection to Gmail. Settings() genuinely shouldn't read a developer's
# local .env at all in tests — only explicit, per-test configuration
# should apply — so env_file loading is disabled here, process-wide, for
# the whole test session.
from app.core.config import Settings  # noqa: E402

Settings.model_config["env_file"] = None

from app.api.deps import get_object_storage  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services.storage import LocalFilesystemStorage, ObjectStorage  # noqa: E402

# A fresh in-memory SQLite database per test keeps tests isolated and fast,
# while still exercising the real SQLAlchemy models and queries used
# against Postgres in staging/production.
TEST_DATABASE_URL = "sqlite+aiosqlite://"


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    async with session_maker() as session:
        yield session

    app.dependency_overrides.pop(get_db, None)
    await engine.dispose()


@pytest.fixture
def test_storage() -> Generator[ObjectStorage, None, None]:
    with tempfile.TemporaryDirectory() as tmp_dir:
        storage = LocalFilesystemStorage(tmp_dir)
        app.dependency_overrides[get_object_storage] = lambda: storage
        yield storage
        app.dependency_overrides.pop(get_object_storage, None)


@pytest_asyncio.fixture
async def client(
    db_session: AsyncSession, test_storage: ObjectStorage
) -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
