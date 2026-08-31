from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


async def migrate_provider_keys(conn: AsyncConnection) -> None:
    """Make external IDs unique per data provider.

    The project initially stored API-Football IDs as globally unique. SStats has
    its own ID namespace, so existing rows are marked as api-football and new
    uniqueness is enforced by (provider, provider_id).
    """
    statements = [
        "ALTER TABLE tournaments ADD COLUMN IF NOT EXISTS provider VARCHAR(32) NOT NULL DEFAULT 'api-football'",
        "ALTER TABLE teams ADD COLUMN IF NOT EXISTS provider VARCHAR(32) NOT NULL DEFAULT 'api-football'",
        "ALTER TABLE matches ADD COLUMN IF NOT EXISTS provider VARCHAR(32) NOT NULL DEFAULT 'api-football'",
        "ALTER TABLE tournaments DROP CONSTRAINT IF EXISTS tournaments_provider_id_key",
        "ALTER TABLE teams DROP CONSTRAINT IF EXISTS teams_provider_id_key",
        "ALTER TABLE matches DROP CONSTRAINT IF EXISTS uq_matches_provider_id",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_tournaments_provider_external_id ON tournaments (provider, provider_id)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_teams_provider_external_id ON teams (provider, provider_id)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_matches_provider_external_id ON matches (provider, provider_id)",
    ]
    for statement in statements:
        await conn.execute(text(statement))
