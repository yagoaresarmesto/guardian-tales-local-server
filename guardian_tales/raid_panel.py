# SPDX-License-Identifier: Apache-2.0
"""Compatibility import for the original Raid panel server."""

from .web_panel.server import WebPanel as RaidPanel

__all__ = ["RaidPanel"]
