"""Application version metadata, surfaced in the admin UI.

We are pre-1.0. The version tracks the minor/major/patch work done while
building the platform out (scaffold, engine port, agent-first UI, dark mode,
multi-environment selector, editable rules page, live scanning fixes). A CI
pipeline can inject BUILD_DATE / BUILD_TIME; otherwise the constants below are
the released stamp for the current build.
"""
from __future__ import annotations

import os

APP_VERSION = "0.6.0"

# Release/build date (YYYY-MM-DD) and clock time (HH:MM, local build tz).
BUILD_DATE = os.environ.get("BUILD_DATE", "2026-08-05")
BUILD_TIME = os.environ.get("BUILD_TIME", "12:40 AEST")
