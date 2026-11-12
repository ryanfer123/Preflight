"""Run the explicit five-document live provider smoke test outside CI."""

from preflight.smoke import main

if __name__ == "__main__":
    raise SystemExit(main())
