from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, AsyncSession
from sqlalchemy.orm import DeclarativeBase

from app.config import DATABASE_URL


def _make_async_database_url(database_url: str) -> URL:
    url = make_url(database_url)
    if url.get_backend_name() in {"postgres", "postgresql"}:
        query = dict(url.query)
        sslmode = query.pop("sslmode", None)
        query.setdefault("ssl", sslmode or "require")
        url = url.set(drivername="postgresql+asyncpg", query=query)
    return url


engine = create_async_engine(_make_async_database_url(DATABASE_URL), echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:  # type: ignore[misc]
    async with async_session() as session:
        yield session


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
