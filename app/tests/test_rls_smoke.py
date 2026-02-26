import os

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_RLS_TESTS") != "1",
    reason="Set RUN_RLS_TESTS=1 and DATABASE_URL to execute DB-level RLS smoke tests.",
)


@pytest.mark.asyncio
async def test_rls_tables_are_queryable_with_session_scope() -> None:
    import asyncpg

    database_url = os.getenv("DATABASE_URL")
    assert database_url, "DATABASE_URL must be set when RUN_RLS_TESTS=1"

    conn = await asyncpg.connect(database_url)
    try:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.user_id', $1, true)", "1")
            await conn.execute("SELECT set_config('app.customer_id', $1, true)", "1")

            for table in ("user", "customer", "ticket", "ticket_item"):
                row = await conn.fetchrow(f'SELECT COUNT(*) AS c FROM "{table}"')
                assert row is not None
                assert int(row["c"]) >= 0
    finally:
        await conn.close()

