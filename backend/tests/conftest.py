"""Shared fixtures.

Database-backed tests run only when TEST_DATABASE_URL points at a migrated
Postgres with pgvector (e.g. the docker-compose database); otherwise they skip.
Each test runs inside a transaction that is rolled back.
"""
import os

import pytest


@pytest.fixture
def pg_session():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set")
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    engine = create_engine(url)
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
        engine.dispose()
