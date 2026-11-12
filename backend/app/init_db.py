"""Create all tables:  python -m app.init_db   (use --reset to drop everything first; DESTRUCTIVE)."""
import sys

from app.database import engine
from app.models import Base


def main() -> None:
    if "--reset" in sys.argv:
        Base.metadata.drop_all(engine)
        print("Dropped all tables.")
    Base.metadata.create_all(engine)
    print("Tables ready:", ", ".join(sorted(Base.metadata.tables)))


if __name__ == "__main__":
    main()
