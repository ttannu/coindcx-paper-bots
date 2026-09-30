import json
import os
import urllib.request

API = "https://api.github.com"


class GitHub:
    def __init__(self, token, repo):
        self.token = token
        self.repo = repo

    @classmethod
    def from_env(cls):
        token, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
        return cls(token, repo) if token and repo else None

    def _call(self, method, path, body=None):
        request = urllib.request.Request(
            API + path,
            method=method,
            data=None if body is None else json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": "Bearer " + self.token,
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "coindcx-paper-bots",
            },
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read()
        return json.loads(raw) if raw else {}

    def create_issue(self, title, body):
        return self._call("POST", "/repos/%s/issues" % self.repo, {"title": title, "body": body})["number"]

    def comment(self, number, body):
        self._call("POST", "/repos/%s/issues/%d/comments" % (self.repo, number), {"body": body})

    def close_issue(self, number, title):
        self._call("PATCH", "/repos/%s/issues/%d" % (self.repo, number), {"state": "closed", "title": title})

    def disable_workflow(self, file_name):
        self._call("PUT", "/repos/%s/actions/workflows/%s/disable" % (self.repo, file_name))
