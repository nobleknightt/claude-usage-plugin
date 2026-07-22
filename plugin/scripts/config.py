"""Runtime configuration for the usage tracker hook scripts.

Values set at plugin install (`--config API_KEY=... BASE_URL=...`) are exposed
to hook processes as `CLAUDE_PLUGIN_OPTION_*` environment variables. Per-user data
lives under the plugin's own `CLAUDE_PLUGIN_DATA` directory.
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Self

CLAUDE_JSON = Path.home() / ".claude.json"


def _plugin_data_dir() -> Path:
    """Return the plugin's persistent data directory.

    Claude Code injects ``CLAUDE_PLUGIN_DATA`` into every hook process. It points
    at ``~/.claude/plugins/data/<plugin-id>/``, survives plugin updates, and is
    cleaned up on uninstall — so it is the correct home for our queue and logs.
    """
    return Path(os.environ["CLAUDE_PLUGIN_DATA"])


@dataclass(slots=True)
class Config:
    api_key: str
    base_url: str
    data_dir: Path

    @classmethod
    def load(cls) -> Self:
        """Load configuration from the plugin's environment variables.

        Returns:
            A populated :class:`Config` instance.
        """
        return cls(
            api_key=os.environ.get("CLAUDE_PLUGIN_OPTION_API_KEY", "").strip(),
            base_url=os.environ.get("CLAUDE_PLUGIN_OPTION_BASE_URL", "").strip().rstrip("/"),
            data_dir=_plugin_data_dir(),
        )

    @property
    def db_path(self) -> Path:
        return self.data_dir / "events.db"

    @property
    def log_path(self) -> Path:
        return self.data_dir / "logs" / "tracker.log"


def read_account_email() -> str:
    """Read the currently logged-in Claude account email from ~/.claude.json.

    Read live rather than cached: the logged-in account can change (re-login,
    machine handed over), and it is the account usage is billed against.

    Returns:
        The account email address, or an empty string if it cannot be read.
    """
    try:
        data = json.loads(CLAUDE_JSON.read_text(encoding="utf-8-sig"))
        return data.get("oauthAccount", {}).get("emailAddress", "")
    except (OSError, json.JSONDecodeError, AttributeError):
        return ""
