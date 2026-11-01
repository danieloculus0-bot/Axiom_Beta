"""Dedicated Windows desktop launcher for the Axiom EWI operator station.

Starts the same tested local Axiom backend; opens directly to the EWI screen.
No external service is exposed by default.
"""
from __future__ import annotations

import os

os.environ.setdefault("AXIOM_START_PATH", "/ewi")
from desktop import main  # noqa: E402

if __name__ == "__main__":
    main()
