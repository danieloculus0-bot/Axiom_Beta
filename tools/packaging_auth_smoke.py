"""Authenticated deployment smoke. Requires provisioned AXIOM_USERS_JSON."""

import argparse
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar


def check(base):
    anonymous = urllib.request.build_opener()
    try:
        anonymous.open(urllib.request.Request(base + "/jobs", data=b"job_number=test"), timeout=10)
    except urllib.error.HTTPError as exc:
        assert exc.code == 401
    else:
        raise AssertionError("anonymous change was not denied")
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
    login = opener.open(base + "/login", timeout=10).read().decode()
    token = re.search(r'name="_csrf" value="([^"]+)"', login).group(1)
    payload = urllib.parse.urlencode({"username": os.environ["AXIOM_SMOKE_USER"],
        "password": os.environ["AXIOM_SMOKE_PASSWORD"], "_csrf": token}).encode()
    result = opener.open(urllib.request.Request(base + "/login", data=payload), timeout=10)
    assert result.geturl().rstrip("/") == base.rstrip("/"), result.geturl()
    health = json.load(opener.open(base + "/health", timeout=10))
    assert health.get("app") == "Axiom" and health.get("ok") is True
    for page in ("payroll", "accounting", "sheets", "quality", "methods", "reports"):
        result = opener.open(base + "/" + page, timeout=15)
        assert result.status == 200 and "/login" not in result.geturl(), page
    print("Authenticated packaging smoke PASS")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("base")
    check(p.parse_args().base)
