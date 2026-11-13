"""Install the pinned private server-platform package during a Render build.

Required environment variables:
  SERVER_PLATFORM_APP_ID
  SERVER_PLATFORM_INSTALLATION_ID
  SERVER_PLATFORM_APP_PRIVATE_KEY

The GitHub App must be installed on server-platform with Contents: read only.
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import time
from urllib.request import Request, urlopen

import jwt

OWNER = "nguyenanhtuan081196"
REPOSITORY = "server-platform"
PLATFORM_REF = "b928015c10a332fa783e76e9160db2e9336d6085"


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def create_installation_token() -> str:
    app_id = required_env("SERVER_PLATFORM_APP_ID")
    installation_id = required_env("SERVER_PLATFORM_INSTALLATION_ID")
    private_key = required_env("SERVER_PLATFORM_APP_PRIVATE_KEY").replace("\\n", "\n")

    now = int(time.time())
    app_jwt = jwt.encode(
        {"iat": now - 60, "exp": now + 540, "iss": app_id},
        private_key,
        algorithm="RS256",
    )
    request = Request(
        f"https://api.github.com/app/installations/{installation_id}/access_tokens",
        data=json.dumps({"permissions": {"contents": "read"}}).encode("utf-8"),
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {app_jwt}",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    token = payload.get("token")
    if not token:
        raise RuntimeError("GitHub did not return an installation access token")
    return token


def main() -> None:
    token = create_installation_token()
    basic_auth = base64.b64encode(f"x-access-token:{token}".encode("utf-8")).decode("ascii")

    env = os.environ.copy()
    # Git's extraheader keeps the short-lived token out of the clone URL and pip arguments.
    env["GIT_CONFIG_COUNT"] = "1"
    env["GIT_CONFIG_KEY_0"] = "http.https://github.com/.extraheader"
    env["GIT_CONFIG_VALUE_0"] = f"AUTHORIZATION: basic {basic_auth}"
    env["GIT_TERMINAL_PROMPT"] = "0"

    package = (
        f"server-platform @ "
        f"git+https://github.com/{OWNER}/{REPOSITORY}.git@{PLATFORM_REF}"
    )
    subprocess.run(
        [sys.executable, "-m", "pip", "install", package],
        check=True,
        env=env,
    )


if __name__ == "__main__":
    main()
