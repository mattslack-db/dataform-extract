import subprocess
import pytest
from dataform_extract.auth import get_access_token, AuthError


class FakeCompleted:
    def __init__(self, returncode, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_returns_stripped_token():
    def runner(cmd, capture_output, text):
        assert cmd == ["gcloud", "auth", "print-access-token"]
        return FakeCompleted(0, stdout="ya29.token-value\n")
    assert get_access_token(runner=runner) == "ya29.token-value"


def test_raises_when_gcloud_missing():
    def runner(cmd, capture_output, text):
        raise FileNotFoundError("gcloud")
    with pytest.raises(AuthError):
        get_access_token(runner=runner)


def test_raises_on_nonzero_exit():
    def runner(cmd, capture_output, text):
        return FakeCompleted(1, stdout="", stderr="not logged in")
    with pytest.raises(AuthError):
        get_access_token(runner=runner)
