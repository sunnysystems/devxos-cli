"""Push metrics to the DevXOS platform."""

import json
import urllib.request
import urllib.error


def push_metrics(
    server_url: str,
    token: str,
    repository: str,
    metrics_path: str,
    window_days: int = 90,
    remote_url: str | None = None,
    cli_version: str | None = None,
) -> dict:
    """Push a metrics.json file to the DevXOS platform.

    Returns the server response as a dict.
    Raises RuntimeError on failure.
    """
    with open(metrics_path) as f:
        metrics = json.load(f)

    payload = {
        "repository": repository,
        "window_days": window_days,
        "metrics": metrics,
    }
    if remote_url:
        payload["remote_url"] = remote_url
    if cli_version:
        payload["cli_version"] = cli_version

    url = f"{server_url.rstrip('/')}/api/ingest"
    data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Push failed (HTTP {e.code}): {body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Push failed: {e.reason}") from e
