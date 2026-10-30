"""Opt-in JobBOSS² hosted Public API reader for Axiom EWI.

No SQL writes. Credentials are supplied by the machine's environment, never
stored in an Axiom record or committed to source control. This connector is
disabled until explicitly configured by an administrator.
"""
from __future__ import annotations

import json
import os
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API_HOST = "https://api-jb2.integrations.ecimanufacturing.com"
TOKEN_URL = "https://api-user.integrations.ecimanufacturing.com/oauth2/api-user/token"


class JobBossError(RuntimeError):
    """An ERP integration failure without exposing credentials."""


def configured() -> bool:
    return bool(os.getenv("AXIOM_JB2_CLIENT_ID") and os.getenv("AXIOM_JB2_CLIENT_SECRET"))


class JobBoss2Reader:
    def __init__(self, *, transport=None):
        self.transport = transport or urlopen
        if not configured():
            raise JobBossError("JobBOSS² API credentials are not configured")

    def _json(self, request: Request) -> object:
        try:
            with self.transport(request, timeout=12) as response:
                return json.load(response)
        except Exception as exc:
            raise JobBossError("JobBOSS² request failed; verify ECI API access and connectivity") from exc

    def _token(self) -> str:
        # Public API user OAuth client credentials (not a JobBOSS employee password).
        body = urlencode({
            "grant_type": "client_credentials",
            "scope": "openid",
            "client_id": os.environ["AXIOM_JB2_CLIENT_ID"],
            "client_secret": os.environ["AXIOM_JB2_CLIENT_SECRET"],
        }).encode("ascii")
        request = Request(TOKEN_URL, data=body, method="POST", headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        })
        payload = self._json(request)
        if not isinstance(payload, dict) or not payload.get("access_token"):
            raise JobBossError("ECI authentication did not return an access token")
        return str(payload["access_token"])

    @staticmethod
    def _items(payload: object) -> list[dict]:
        if isinstance(payload, list):
            return [x for x in payload if isinstance(x, dict)]
        if isinstance(payload, dict):
            for key in ("data", "items", "results", "value"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [x for x in value if isinstance(x, dict)]
                if isinstance(value, dict):
                    return JobBoss2Reader._items(value)
        raise JobBossError("Unrecognized JobBOSS² route response; review API mapping")

    def routes(self, job_number: str) -> list[dict]:
        if not job_number.strip():
            raise ValueError("Job number is required")
        token = self._token()
        matches: list[dict] = []
        # Bound reads; exact-match locally even if remote filters are ignored.
        for skip in range(0, 1000, 200):
            url = API_HOST + "/api/v1/order-routings?" + urlencode({
                "jobNumber[eq]": job_number, "take": 200, "skip": skip,
            })
            request = Request(url, headers={"Authorization": "Bearer " + token,
                                             "Accept": "application/json"})
            page = self._items(self._json(request))
            for item in page:
                if str(item.get("jobNumber", "")).strip() != job_number:
                    continue
                step = item.get("stepNumber")
                if step is None or not str(step).strip():
                    continue
                matches.append({
                    "step": str(step),
                    "operation": str(item.get("operationCode") or "").strip(),
                    "work_center": str(item.get("workCenter") or "").strip(),
                    "instruction": str(item.get("description") or "").strip(),
                    "external_id": str(item.get("uniqueID") or "").strip(),
                    "part_number": str(item.get("partNumber") or "").strip(),
                })
            if len(page) < 200:
                break
        else:
            raise JobBossError("Routing result exceeds bounded scan; narrow the ERP query")
        return matches
