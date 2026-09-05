from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


async def migrate_provider_keys(conn: AsyncConnection) -> None:
    """Apply lightweight idempotent schema migrations used by the app."""
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

        "ALTER TABLE oracle_predictions ADD COLUMN IF NOT EXISTS locked_at TIMESTAMPTZ NULL",
        "CREATE INDEX IF NOT EXISTS ix_oracle_predictions_locked_at ON oracle_predictions (locked_at)",
        "ALTER TABLE players ADD COLUMN IF NOT EXISTS has_photo BOOLEAN NOT NULL DEFAULT FALSE",
        "CREATE INDEX IF NOT EXISTS ix_players_has_photo ON players (has_photo)",
    ]
    for statement in statements:
        await conn.execute(text(statement))
