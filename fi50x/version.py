"""Single source of truth for the package version.

Kept dependency-free and assignment-only so it can be read by static analysis
(setuptools' dynamic version in pyproject, and the release workflow's grep)
without importing the package.
"""

__version__ = "0.2.0"
