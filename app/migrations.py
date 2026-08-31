from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


async def migrate_provider_keys(conn: AsyncConnection) -> None:
    """Make external IDs unique per data provider.

    The project initially stored API-Football IDs as globally unique. SStats has
    its own ID namespace, so existing rows are marked as api-football and new
    uniqueness is enforced by (provider, provider_id).

    Older SQLAlchemy metadata may have created provider_id uniqueness either as
    a table constraint or as a unique ix_* index. Drop both forms before
    creating the composite provider-aware indexes.
    """
    statements = [
        "ALTER TABLE tournaments ADD COLUMN IF NOT EXISTS provider VARCHAR(32) NOT NULL DEFAULT 'api-football'",
        "ALTER TABLE teams ADD COLUMN IF NOT EXISTS provider VARCHAR(32) NOT NULL DEFAULT 'api-football'",
        "ALTER TABLE matches ADD COLUMN IF NOT EXISTS provider VARCHAR(32) NOT NULL DEFAULT 'api-football'",

        "ALTER TABLE tournaments DROP CONSTRAINT IF EXISTS tournaments_provider_id_key",
        "ALTER TABLE teams DROP CONSTRAINT IF EXISTS teams_provider_id_key",
        "ALTER TABLE matches DROP CONSTRAINT IF EXISTS matches_provider_id_key",
        "ALTER TABLE matches DROP CONSTRAINT IF EXISTS uq_matches_provider_id",

        "DROP INDEX IF EXISTS ix_tournaments_provider_id",
        "DROP INDEX IF EXISTS ix_teams_provider_id",
        "DROP INDEX IF EXISTS ix_matches_provider_id",

        "CREATE INDEX IF NOT EXISTS ix_tournaments_provider_id ON tournaments (provider_id)",
        "CREATE INDEX IF NOT EXISTS ix_teams_provider_id ON teams (provider_id)",
        "CREATE INDEX IF NOT EXISTS ix_matches_provider_id ON matches (provider_id)",

        "CREATE UNIQUE INDEX IF NOT EXISTS uq_tournaments_provider_external_id ON tournaments (provider, provider_id)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_teams_provider_external_id ON teams (provider, provider_id)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_matches_provider_external_id ON matches (provider, provider_id)",
    ]
    for statement in statements:
        await conn.execute(text(statement))
