"""Block until MySQL (with the seeded trusted DB) and Floci S3 answer, or fail after a timeout."""

import sys
import time

from sqlalchemy import create_engine, text

from meridian.aws import s3_client
from meridian.config import get_settings

TIMEOUT_S = 180


def wait(name: str, probe) -> None:  # type: ignore[no-untyped-def]
    deadline = time.monotonic() + TIMEOUT_S
    while True:
        try:
            probe()
            print(f"{name}: ready")
            return
        except Exception as exc:
            if time.monotonic() > deadline:
                sys.exit(f"{name}: not ready after {TIMEOUT_S}s ({exc})")
            time.sleep(3)


def main() -> None:
    s = get_settings()
    engine = create_engine(s.trusted_db_url)

    def mysql_seeded() -> None:
        with engine.connect() as conn:
            n = conn.execute(text("SELECT COUNT(*) FROM orders")).scalar_one()
            if n < 20_000:
                raise RuntimeError(f"still seeding ({n} orders)")

    wait("floci", lambda: s3_client(s).list_buckets())
    wait("mysql", mysql_seeded)


if __name__ == "__main__":
    main()
