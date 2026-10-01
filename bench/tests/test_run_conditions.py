"""Azure run-condition recording: host redaction and user-reported CPU credits."""
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "bench"))

import run_bench as RB  # noqa: E402


class FakeDB:
    conn = SimpleNamespace(info=SimpleNamespace(ssl_in_use=True))

    def scalar(self, sql, params=None):
        return "x"


def _env(monkeypatch, env, url):
    monkeypatch.setenv("DATABASE_URL", url)
    args = SimpleNamespace(env=env, dry_run=False)
    return RB.environment(FakeDB(), args, ROOT / "bench/corpus/cuad_corpus_meta.json",
                          ROOT / "bench/corpus/cuad_split.json", 1, 1)


def test_azure_host_is_redacted(monkeypatch):
    secret_host = "myserver.postgres.database.azure.com"
    out = _env(monkeypatch, "azure", f"postgresql://u:pw@{secret_host}:5432/postgres?sslmode=require")
    assert out["db_host"] == "<azure-flexible-server>"
    assert secret_host not in repr(out)
    assert "pw" not in {str(v) for v in out.values()}


def test_local_host_is_kept(monkeypatch):
    out = _env(monkeypatch, "local", "postgresql://lexora:lexora123@postgres:5432/lexora")
    assert out["db_host"] == "postgres"


def test_credit_answers_are_recorded_verbatim():
    answers = iter(["  1234.5 ", "15:42 CDT"])
    out = RB.ask_credits("before", input_fn=lambda prompt: next(answers))
    assert out["source"] == "user-reported from Azure portal"
    assert out["metric"].startswith("CPU Credits Remaining")
    assert out["value_as_entered"] == "1234.5"
    assert out["data_point_time_as_entered"] == "15:42 CDT"


def test_blank_credit_answer_is_null_not_guessed():
    out = RB.ask_credits("after", input_fn=lambda prompt: "")
    assert out["value_as_entered"] is None
    assert out["data_point_time_as_entered"] is None
