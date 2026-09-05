from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


async def migrate_provider_keys(conn: AsyncConnection) -> None:
    """Apply lightweight idempotent schema migrations used by the app."""
    statements = [
        "ALTER TABLE tournaments ADD COLUMN IF NOT EXISTS provider VARCHAR(32) NOT NULL DEFAULT 'sstats'",
        "ALTER TABLE teams ADD COLUMN IF NOT EXISTS provider VARCHAR(32) NOT NULL DEFAULT 'sstats'",
        "ALTER TABLE matches ADD COLUMN IF NOT EXISTS provider VARCHAR(32) NOT NULL DEFAULT 'sstats'",
        "ALTER TABLE teams ADD COLUMN IF NOT EXISTS source_name VARCHAR(150) NULL",
        "ALTER TABLE teams ADD COLUMN IF NOT EXISTS country_code VARCHAR(16) NULL",
        "ALTER TABLE teams ADD COLUMN IF NOT EXISTS uefa_id INTEGER NULL",
        "CREATE INDEX IF NOT EXISTS ix_teams_source_name ON teams (source_name)",
        "CREATE INDEX IF NOT EXISTS ix_teams_uefa_id ON teams (uefa_id)",
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
        "ALTER TABLE players ADD COLUMN IF NOT EXISTS shirt_number INTEGER NULL",
        "ALTER TABLE players ADD COLUMN IF NOT EXISTS nationality VARCHAR(64) NULL",
        "ALTER TABLE players ALTER COLUMN nationality TYPE VARCHAR(64)",
        "CREATE INDEX IF NOT EXISTS ix_players_has_photo ON players (has_photo)",
        "ALTER TABLE tournament_predictions ADD COLUMN IF NOT EXISTS top_scorer_player_id INTEGER NULL REFERENCES players(id) ON DELETE SET NULL",
        "ALTER TABLE tournament_predictions ADD COLUMN IF NOT EXISTS top_assistant_player_id INTEGER NULL REFERENCES players(id) ON DELETE SET NULL",
        "ALTER TABLE tournament_predictions ADD COLUMN IF NOT EXISTS best_player_player_id INTEGER NULL REFERENCES players(id) ON DELETE SET NULL",
        "CREATE INDEX IF NOT EXISTS ix_tournament_predictions_top_scorer_player_id ON tournament_predictions (top_scorer_player_id)",
        "CREATE INDEX IF NOT EXISTS ix_tournament_predictions_top_assistant_player_id ON tournament_predictions (top_assistant_player_id)",
        "CREATE INDEX IF NOT EXISTS ix_tournament_predictions_best_player_id ON tournament_predictions (best_player_player_id)",
    ]
    for statement in statements:
        await conn.execute(text(statement))
