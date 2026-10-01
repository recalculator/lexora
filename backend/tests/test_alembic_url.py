"""Alembic config must accept URLs with percent-encoded passwords."""
import pytest
from alembic.config import Config

from app.db.url import escape_for_alembic_config

# Fake credentials; %40 is "@", %25 is "%", %2F is "/"
URL = "postgresql://user:p%40ss%25w%2Frd@db.example.invalid:5432/app?sslmode=require"


def test_unescaped_percent_breaks_alembic_config():
    config = Config()
    with pytest.raises(ValueError):
        config.set_main_option("sqlalchemy.url", URL)


def test_escaped_url_round_trips_through_alembic_config():
    config = Config()
    config.set_main_option("sqlalchemy.url", escape_for_alembic_config(URL))
    assert config.get_main_option("sqlalchemy.url") == URL


def test_url_without_percent_is_unchanged():
    url = "postgresql://lexora:lexora123@postgres:5432/lexora"
    assert escape_for_alembic_config(url) == url
