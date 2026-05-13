from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


def to_async_db_url(dbstr: str) -> str:
    if dbstr.startswith("postgresql+asyncpg://"):
        return dbstr
    if dbstr.startswith("postgresql://"):
        return dbstr.replace("postgresql://", "postgresql+asyncpg://", 1)
    if dbstr.startswith("postgres://"):
        return dbstr.replace("postgres://", "postgresql+asyncpg://", 1)
    if dbstr.startswith("sqlite+aiosqlite://"):
        return dbstr
    if dbstr.startswith("sqlite://"):
        return dbstr.replace("sqlite://", "sqlite+aiosqlite://", 1)
    return dbstr


def create_session_factory(dbstr: str) -> tuple[async_sessionmaker[AsyncSession], AsyncEngine]:
    """Create an async SQLAlchemy session factory and engine."""
    engine = create_async_engine(to_async_db_url(dbstr), pool_pre_ping=True)
    session_factory = async_sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    return session_factory, engine
