import http.client
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request

API = "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent"
HOUR_MS = 3600000
DAY_MS = 24 * HOUR_MS
BUSY_REST_MS = 15 * 60000
# Free-tier daily quotas reset at midnight Pacific time, 07:00 or 08:00 UTC depending on daylight saving.
QUOTA_RESET_UTC_MS = 8 * HOUR_MS


class LLMError(Exception):
    pass


class KeyRejected(LLMError):
    pass


def _post(url, body, headers, timeout):
    request = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def parse_json(text):
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", text)
    try:
        value = json.loads(text)
    except ValueError:
        start, end = text.find("{"), text.rfind("}")
        try:
            value = json.loads(text[start:end + 1]) if 0 <= start < end else None
        except ValueError:
            value = None
    if not isinstance(value, dict):
        raise LLMError("the answer was not a JSON object")
    return value


def _retry_delay(error):
    for detail in error.get("details", ()):
        delay = detail.get("retryDelay")
        if isinstance(delay, str) and delay.endswith("s"):
            try:
                return float(delay[:-1])
            except ValueError:
                pass
    return None


def _next_quota_reset(now_ms):
    reset = now_ms - now_ms % DAY_MS + QUOTA_RESET_UTC_MS
    return reset if reset > now_ms else reset + DAY_MS


class Gemini:
    """Asks Gemini for JSON, falling back along a list of free-tier models.

    `cooldowns` is saved in the state, so a model that ran out of daily quota is skipped until the quota resets.
    """

    def __init__(self, key, cooldowns, now_ms, timeout=90, transport=_post, sleep=time.sleep):
        self.key = key
        self.cooldowns = cooldowns
        self.now_ms = now_ms
        self.timeout = timeout
        self.transport = transport
        self.sleep = sleep
        self.log = []
        self._lock = threading.Lock()

    @classmethod
    def from_env(cls, cooldowns, now_ms):
        key = (os.environ.get("GEMINI_API_KEY") or "").strip()
        return cls(key, cooldowns, now_ms) if key else None

    def ask(self, role, models, system, prompt, deadline, check=None, thinking="low"):
        """Returns (answer, model). `check` returns a reason to reject an answer, which moves on to the next model."""
        errors = []
        for model in models:
            with self._lock:
                if self.cooldowns.get(model, 0) > self.now_ms:
                    continue
            if time.time() >= deadline:
                errors.append("out of time")
                break
            began = time.time()
            try:
                answer = parse_json(self._generate(model, system, prompt, deadline, thinking))
                problem = check(answer) if check else None
                if problem:
                    raise LLMError(problem)
            except KeyRejected:
                raise
            except LLMError as exc:
                errors.append("%s: %s" % (model, exc))
                self._record(role, model, began, str(exc))
                continue
            self._record(role, model, began, "ok")
            return answer, model
        raise LLMError("; ".join(errors) or "every model is resting until its quota resets")

    def _record(self, role, model, began, outcome):
        with self._lock:
            self.log.append({"role": role, "model": model, "seconds": round(time.time() - began, 1), "outcome": outcome[:160]})

    def _cool(self, model, until):
        with self._lock:
            self.cooldowns[model] = max(self.cooldowns.get(model, 0), until)

    def _generate(self, model, system, prompt, deadline, thinking):
        config = {"temperature": 0.4, "responseMimeType": "application/json"}
        if thinking and model.startswith("gemini-3"):
            config["thinkingConfig"] = {"thinkingLevel": thinking}
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": config,
        }
        headers = {"x-goog-api-key": self.key, "Content-Type": "application/json", "User-Agent": "coindcx-paper-bots"}
        waited = False
        while True:
            timeout = min(self.timeout, deadline - time.time())
            if timeout < 5:
                raise LLMError("out of time")
            try:
                data = self.transport(API % model, body, headers, timeout)
                break
            except urllib.error.HTTPError as exc:
                error = self._error_body(exc)
                message = self._hide(str(error.get("message") or exc.reason))[:200]
                if exc.code in (401, 403) or (exc.code == 400 and "API key" in message):
                    raise KeyRejected("the API key was rejected (HTTP %d): %s" % (exc.code, message))
                if exc.code == 429:
                    delay = _retry_delay(error)
                    daily = "PerDay" in json.dumps(error)
                    if not daily and not waited and delay is not None and delay <= 30 and time.time() + delay + 10 < deadline:
                        waited = True
                        self.sleep(delay + 1)
                        continue
                    self._cool(model, _next_quota_reset(self.now_ms) if daily else self.now_ms + 5 * 60000)
                    raise LLMError("quota used up (HTTP 429)")
                if exc.code == 404:
                    self._cool(model, self.now_ms + DAY_MS)
                    raise LLMError("model not available (HTTP 404): %s" % message)
                if exc.code in (500, 502, 503, 504):
                    # An overloaded model rarely recovers within a meeting, so the desk's later calls skip it.
                    self._cool(model, self.now_ms + BUSY_REST_MS)
                    raise LLMError("HTTP %d: %s" % (exc.code, message))
                if exc.code == 400 and "thinkingConfig" in config and "think" in message.lower():
                    del config["thinkingConfig"]
                    continue
                raise LLMError("HTTP %d: %s" % (exc.code, message))
            except (OSError, ValueError, http.client.HTTPException) as exc:
                raise LLMError("%s: %s" % (type(exc).__name__, self._hide(str(exc))[:200]))
        candidates = data.get("candidates") or []
        if not candidates:
            raise LLMError("no answer (%s)" % (data.get("promptFeedback", {}).get("blockReason") or "empty response"))
        parts = (candidates[0].get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        if not text.strip():
            raise LLMError("empty answer (%s)" % candidates[0].get("finishReason"))
        return text

    def _error_body(self, exc):
        try:
            return json.loads(exc.read().decode("utf-8", "replace")).get("error") or {}
        except (OSError, ValueError, AttributeError):
            return {}

    def _hide(self, text):
        return text.replace(self.key, "[hidden]") if self.key else text
