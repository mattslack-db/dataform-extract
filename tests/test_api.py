import json
import pytest
from dataform_extract.api import DataformClient, ApiError, BASE_URL

REPO = "projects/p/locations/us/repositories/r"

class RecordingOpener:
    """Returns queued responses and records requests."""
    def __init__(self, responses):
        self._responses = list(responses)   # list of (status, dict)
        self.calls = []
    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, headers, body))
        status, payload = self._responses.pop(0)
        return status, json.dumps(payload).encode()

def test_create_compilation_result_with_commitish():
    opener = RecordingOpener([(200, {"name": f"{REPO}/compilationResults/abc"})])
    client = DataformClient("tok", opener=opener)
    name = client.create_compilation_result(REPO, commitish="main")
    assert name == f"{REPO}/compilationResults/abc"
    method, url, headers, body = opener.calls[0]
    assert method == "POST"
    assert url == f"{BASE_URL}/{REPO}/compilationResults"
    assert headers["Authorization"] == "Bearer tok"
    assert json.loads(body) == {"gitCommitish": "main"}

def test_create_compilation_result_with_workspace():
    opener = RecordingOpener([(200, {"name": "x"})])
    client = DataformClient("tok", opener=opener)
    client.create_compilation_result(REPO, workspace="ws")
    _, _, _, body = opener.calls[0]
    assert json.loads(body) == {"workspace": f"{REPO}/workspaces/ws"}

def test_query_actions_follows_pagination():
    name = f"{REPO}/compilationResults/abc"
    opener = RecordingOpener([
        (200, {"compilationResultActions": [{"filePath": "a"}], "nextPageToken": "t2"}),
        (200, {"compilationResultActions": [{"filePath": "b"}]}),
    ])
    client = DataformClient("tok", opener=opener)
    actions = client.query_actions(name)
    assert [a["filePath"] for a in actions] == ["a", "b"]
    assert opener.calls[0][1] == f"{BASE_URL}/{name}:query"
    assert "pageToken=t2" in opener.calls[1][1]

def test_non_2xx_raises_api_error():
    opener = RecordingOpener([(403, {"error": {"message": "denied"}})])
    client = DataformClient("tok", opener=opener)
    with pytest.raises(ApiError) as exc:
        client.create_compilation_result(REPO, commitish="main")
    assert "403" in str(exc.value)
