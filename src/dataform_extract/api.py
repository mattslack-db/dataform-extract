"""Minimal Dataform REST client: create a compilation result and query its actions."""
import json
import urllib.error
import urllib.request
from urllib.parse import quote

BASE_URL = "https://dataform.googleapis.com/v1beta1"


class ApiError(Exception):
    """Raised on a non-2xx response from the Dataform API."""


def _default_opener(method: str, url: str, headers: dict, body: bytes | None):
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


class DataformClient:
    def __init__(self, token: str, opener=_default_opener, base_url: str = BASE_URL):
        self._token = token
        self._opener = opener
        self._base = base_url

    def _request(self, method: str, url: str, body: dict | None = None) -> dict:
        headers = {"Authorization": f"Bearer {self._token}"}
        raw_body = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            raw_body = json.dumps(body).encode()
        status, payload = self._opener(method, url, headers, raw_body)
        if not 200 <= status < 300:
            raise ApiError(f"HTTP {status} from {url}: {payload.decode(errors='replace')}")
        return json.loads(payload) if payload else {}

    def create_compilation_result(self, repo: str, *, commitish: str | None = None,
                                  workspace: str | None = None) -> str:
        url = f"{self._base}/{repo}/compilationResults"
        if commitish is not None:
            body = {"gitCommitish": commitish}
        else:
            body = {"workspace": f"{repo}/workspaces/{workspace}"}
        return self._request("POST", url, body)["name"]

    def query_actions(self, compilation_result_name: str) -> list[dict]:
        actions: list[dict] = []
        page_token: str | None = None
        while True:
            url = f"{self._base}/{compilation_result_name}:query"
            if page_token:
                url += f"?pageToken={quote(page_token)}"
            data = self._request("GET", url)
            actions.extend(data.get("compilationResultActions", []))
            page_token = data.get("nextPageToken")
            if not page_token:
                return actions
