"""Package inventory and management for Argos Translate."""
from __future__ import annotations

import logging
from typing import Dict, List, Set, Tuple

log = logging.getLogger("agent04.providers.argos.packages")


class ArgosPackageManager:
    """Discovers and inspects installed Argos language packages."""

    @staticmethod
    def get_installed_pairs() -> Set[Tuple[str, str]]:
        """Returns set of (from_code, to_code) pairs installed in the local environment."""
        try:
            import argostranslate.package
            packages = argostranslate.package.get_installed_packages()
            pairs = set()
            for p in packages:
                pairs.add((p.from_code, p.to_code))
            return pairs
        except Exception as e:
            log.warning(f"Failed to query installed Argos packages: {e}")
            return set()

    @staticmethod
    def is_pair_installed(from_code: str, to_code: str) -> bool:
        pairs = ArgosPackageManager.get_installed_pairs()
        return (from_code, to_code) in pairs

