"""Database URL helpers."""


def escape_for_alembic_config(database_url: str) -> str:
    """Escape % for Alembic's configparser-backed Config.

    Config.set_main_option interpolates values, so a percent-encoded password
    (e.g. %40 for @) raises "invalid interpolation syntax" unless % is doubled.
    get_main_option returns the original, unescaped URL.
    """
    return database_url.replace("%", "%%")
