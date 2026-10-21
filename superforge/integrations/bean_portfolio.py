"""Opt-in Axiom to BEAN portfolio learning with a real separate Core checkout.

Does not install a second learner in each ERP module. This adapter sends
whitelisted, anonymized, explicitly-scored outcomes to BEAN research Core.
No raw customer drawings, personnel records or private event payloads passed.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys

ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,159}$")


def _safe(value, label):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValueError(f"Invalid {label}")
    return value


class BeanPortfolioClient:
    def __init__(self, core_dir: str | Path, db_path: str | Path):
        self.core_dir = Path(core_dir).resolve()
        self.db_path = Path(db_path).resolve()
        if not (self.core_dir / "bean/optimization/portfolio_cli.py").is_file():
            raise ValueError("Expected experimental BEAN Portfolio CLI checkout")

    def _run(self, command: str, args=(), payload=None) -> dict:
        env = {"PYTHONPATH":str(self.core_dir),"PATH":os.environ.get("PATH",""),
               "PYTHONDONTWRITEBYTECODE":"1","PYTHONIOENCODING":"utf-8"}
        if os.name=="nt":
            env["SYSTEMROOT"]=os.environ.get("SYSTEMROOT","")
            env["TEMP"]=os.environ.get("TEMP","")
        proc = subprocess.run(
            [sys.executable,"-m","bean.optimization.portfolio_cli",command,
             "--db",str(self.db_path),*args],
            input=json.dumps(payload) if payload is not None else None,
            cwd=self.core_dir,env=env,text=True,capture_output=True,
            check=True,timeout=20)
        return json.loads(proc.stdout)

    def observe(self, *, module: str, event_id: str, state: str,
                action: str | None=None, reward: float | None=None,
                next_state: str | None=None, done=False,
                evidence_ref: str, kind="unverified", revision="unspecified"):
        """Append an anonymized event. Only explicit rewards update learned Q.

        Never calculate rewards from status='passed' or a user's unsupported
        claim; callers must establish meaningful outcome metrics separately.
        """
        _safe(module,"module")
        _safe(event_id,"event_id")
        _safe(state,"state")
        _safe(evidence_ref,"evidence_ref")
        return self._run("record",payload={
            "app":f"Axiom_Beta/{module}","event_id":event_id,
            "state":state,"action":action,"reward":reward,
            "next_state":next_state,"done":done,
            "evidence_ref":evidence_ref,"kind":kind,
            "revision":revision})

    def observe_domain_event(self,event):
        """Record domain-event metadata ONLY, without personal or shop data."""
        module=_safe(event.source_module,"source module")
        event_id=_safe(event.event_id,"event ID")
        event_type=_safe(event.event_type,"event type")
        return self.observe(module=module,event_id=event_id,state=event_type,
                            evidence_ref=f"axiom://{event_id}",
                            kind="unverified")

    def context(self, *, module: str, query="", max_bytes=2048):
        return self._run("context",args=(
            "--app",f"Axiom_Beta/{_safe(module,'module')}",
            "--query",query,"--max-bytes",str(max_bytes)))

    def verify(self):
        return self._run("verify")
