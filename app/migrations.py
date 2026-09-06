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
        "ALTER TABLE tournament_predictions ADD COLUMN IF NOT EXISTS tournament_id INTEGER NULL REFERENCES tournaments(id) ON DELETE SET NULL",
        "CREATE INDEX IF NOT EXISTS ix_tournament_predictions_tournament_id ON tournament_predictions (tournament_id)",
        "ALTER TABLE tournament_predictions DROP CONSTRAINT IF EXISTS uq_tournament_prediction_user_competition",
        "DROP INDEX IF EXISTS uq_tournament_prediction_user_competition",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_tournament_prediction_user_tournament_season ON tournament_predictions (user_id, tournament_id, season)",
        "UPDATE tournament_predictions tp SET tournament_id = x.tournament_id FROM (SELECT MIN(tournament_id) AS tournament_id, provider, season FROM matches GROUP BY provider, season) x WHERE tp.tournament_id IS NULL AND tp.provider=x.provider AND tp.season=x.season",
        "ALTER TABLE user_leagues ADD COLUMN IF NOT EXISTS tournament_id INTEGER NULL REFERENCES tournaments(id) ON DELETE SET NULL",
        "CREATE INDEX IF NOT EXISTS ix_user_leagues_tournament_id ON user_leagues (tournament_id)",
        "UPDATE user_leagues ul SET tournament_id = x.tournament_id FROM (SELECT MIN(tournament_id) AS tournament_id, provider, season FROM matches GROUP BY provider, season) x WHERE ul.tournament_id IS NULL AND ul.tournament_provider=x.provider AND ul.tournament_season=x.season",
    ]
    for statement in statements:
        await conn.execute(text(statement))
