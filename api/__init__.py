"""
HTTP surface for the Harara work/rest scheduler.

This package contains no domain logic. It translates HTTP requests into calls
on the deterministic tool layer in `src/agent/` and shapes the results for a
web client. The physics, the optimiser and the ACGIH tables live in `src/` and
are not touched here.
"""

__version__ = "0.1.0"
