from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.storage import database  # noqa: E402


def main() -> None:
    database.reset_database()
    print(f"Reset demo database: {database.resolve_db_path()}")


if __name__ == "__main__":
    main()
