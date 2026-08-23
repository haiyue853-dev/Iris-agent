from pathlib import Path

import pytest


def test_example_environment_contains_only_safe_secret_placeholders():
    example = Path(__file__).parents[2] / ".env.example"
    for raw_line in example.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = (part.strip() for part in line.split("=", 1))
        if any(marker in key.upper() for marker in ("API_KEY", "SECRET", "TOKEN")):
            safe_placeholder = not value or value.lower().startswith(("your-", "example-", "placeholder-"))
            if not safe_placeholder:
                pytest.fail("example environment contains an unsafe secret value")
