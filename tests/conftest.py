"""Pytest configuration. Sets BOT_API_SECRET for auth integration tests when not already set."""

import os

# Set before any test module imports core.config (which reads BOT_API_SECRET)
if not os.getenv("BOT_API_SECRET"):
    os.environ["BOT_API_SECRET"] = "testsecret123"
