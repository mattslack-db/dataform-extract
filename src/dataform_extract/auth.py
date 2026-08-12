"""Obtain a GCP access token via the gcloud CLI."""
import subprocess


class AuthError(Exception):
    """Raised when a gcloud access token cannot be obtained."""


def get_access_token(runner=subprocess.run) -> str:
    cmd = ["gcloud", "auth", "print-access-token"]
    try:
        result = runner(cmd, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise AuthError(
            "gcloud not found on PATH. Install the Google Cloud SDK and run "
            "`gcloud auth login`."
        ) from exc
    if result.returncode != 0:
        raise AuthError(
            "Failed to get access token via gcloud. Run `gcloud auth login`.\n"
            f"{(result.stderr or '').strip()}"
        )
    return result.stdout.strip()
