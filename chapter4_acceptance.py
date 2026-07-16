from __future__ import annotations

# Validation trigger for the idempotent direct-runtime patch.
from tests.production_acceptance import interface_acceptance


def main() -> int:
    interface_acceptance()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
