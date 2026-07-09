"""Single source of truth for the package version.

Kept dependency-free and assignment-only so packaging tools (setuptools'
``dynamic.version = {attr = "fi50x.version.__version__"}``) can read it via static
analysis without importing the whole package.
"""

__version__ = "0.1.0"
