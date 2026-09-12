"""Backward-compatible access to the package version metadata."""

from ..research.version import __release__, __version__

__all__ = ["__version__", "__release__"]
