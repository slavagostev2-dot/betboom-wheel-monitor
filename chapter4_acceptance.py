from __future__ import annotations

# Trigger the queued direct-runtime migration.
from tests.production_acceptance import interface_acceptance


def main() -> int:
    interface_acceptance()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
