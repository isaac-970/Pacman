from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - depends on environment setup
    load_dotenv = None

try:
    from supabase import Client, create_client
except ImportError:  # pragma: no cover - depends on environment setup
    Client = Any
    create_client = None


def _env_file_candidates() -> tuple[Path, ...]:
    source_root = Path(__file__).resolve().parent.parent
    executable_root = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else None
    cwd_root = Path.cwd()

    roots: list[Path] = []
    for root in (executable_root, cwd_root, source_root):
        if root is not None and root not in roots:
            roots.append(root)

    return tuple(root / ".env" for root in roots)


@dataclass(slots=True)
class ScoreEntry:
    player_name: str
    score: int
    stage_reached: int
    played_at: datetime


class LeaderboardConfigError(RuntimeError):
    pass


class LeaderboardServiceError(RuntimeError):
    pass


class LeaderboardService:
    def __init__(self) -> None:
        self.last_error: str | None = None
        self._config = self._read_config()
        self._client: Client | None = None

    def _read_config(self) -> dict[str, str]:
        if load_dotenv is not None:
            for env_file in _env_file_candidates():
                if env_file.exists():
                    load_dotenv(env_file)
                    break

        if create_client is None:
            self.last_error = "Leaderboard unavailable: install supabase."
            return {}

        required_keys = {
            "url": os.getenv("SUPABASE_URL", "").strip(),
            "key": os.getenv("SUPABASE_ANON_KEY", "").strip(),
        }
        table_name = os.getenv("SUPABASE_LEADERBOARD_TABLE", "pacman_scores").strip() or "pacman_scores"

        missing = [name for name, value in required_keys.items() if not value]
        if missing:
            self.last_error = (
                "Leaderboard unavailable: set SUPABASE_URL and SUPABASE_ANON_KEY."
            )
            return {}

        return {
            "url": required_keys["url"],
            "key": required_keys["key"],
            "table": table_name,
        }

    def is_configured(self) -> bool:
        return bool(self._config)

    def _table_name(self) -> str:
        return self._config.get("table", "pacman_scores")

    def _truncate_error_message(self, detail: str) -> str:
        condensed = " ".join(detail.split())
        if len(condensed) <= 120:
            return condensed
        return f"{condensed[:117]}..."

    def _set_runtime_error(self, exc: Exception) -> None:
        message = getattr(exc, "message", None) or str(exc) or exc.__class__.__name__
        if message.startswith("Leaderboard unavailable:"):
            self.last_error = self._truncate_error_message(message)
            return
        self.last_error = f"Leaderboard unavailable: {self._truncate_error_message(message)}"

    def _client_instance(self) -> Client:
        if not self._config:
            raise LeaderboardConfigError(self.last_error or "Leaderboard is not configured.")
        if self._client is None:
            try:
                self._client = create_client(self._config["url"], self._config["key"])
            except Exception as exc:  # pragma: no cover - depends on remote service setup
                self._set_runtime_error(exc)
                raise LeaderboardServiceError(self.last_error or "Could not create leaderboard client.") from exc
        return self._client

    def _parse_played_at(self, value: Any) -> datetime:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str) and value:
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                pass
        return datetime.now(timezone.utc)

    def _score_entry_from_row(self, row: Any) -> ScoreEntry:
        if not isinstance(row, dict):
            raise LeaderboardServiceError("Leaderboard returned an invalid score row.")
        try:
            return ScoreEntry(
                player_name=str(row.get("player_name", "Unknown"))[:32],
                score=int(row.get("score", 0)),
                stage_reached=int(row.get("stage_reached", 0)),
                played_at=self._parse_played_at(row.get("played_at")),
            )
        except (TypeError, ValueError) as exc:
            raise LeaderboardServiceError("Leaderboard returned an invalid score row.") from exc

    def initialize(self) -> None:
        try:
            self._client_instance()
        except (LeaderboardConfigError, LeaderboardServiceError):
            raise

    def fetch_top_scores(self) -> list[ScoreEntry]:
        try:
            self.initialize()
            response = (
                self._client_instance()
                .table(self._table_name())
                .select("player_name, score, stage_reached, played_at")
                .order("score", desc=True)
                .order("stage_reached", desc=True)
                .order("played_at", desc=False)
                .limit(10)
                .execute()
            )
            rows = response.data or []
        except LeaderboardConfigError:
            raise
        except LeaderboardServiceError:
            raise
        except Exception as exc:  # pragma: no cover - depends on remote service setup
            self._set_runtime_error(exc)
            raise LeaderboardServiceError(self.last_error or "Could not load leaderboard scores.") from exc

        self.last_error = None
        return [self._score_entry_from_row(row) for row in rows]

    def qualifies(self, score: int, scores: list[ScoreEntry]) -> bool:
        if score <= 0:
            return False
        if len(scores) < 10:
            return True
        return score > scores[-1].score

    def submit_score(self, player_name: str, score: int, stage_reached: int) -> None:
        cleaned_name = player_name.strip()[:32]
        if not cleaned_name:
            self.last_error = "Player name cannot be empty."
            raise LeaderboardServiceError(self.last_error)

        try:
            self.initialize()
            (
                self._client_instance()
                .table(self._table_name())
                .insert(
                    {
                        "player_name": cleaned_name,
                        "score": int(score),
                        "stage_reached": int(stage_reached),
                        "played_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
                .execute()
            )
        except LeaderboardConfigError:
            raise
        except LeaderboardServiceError:
            raise
        except Exception as exc:  # pragma: no cover - depends on remote service setup
            self._set_runtime_error(exc)
            raise LeaderboardServiceError(self.last_error or "Could not save leaderboard score.") from exc

        self.last_error = None
