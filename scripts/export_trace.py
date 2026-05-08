from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.trace_export import DEFAULT_TRACE_EXPORT_PATH, write_trace_export  # noqa: E402


def main() -> None:
    output_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_TRACE_EXPORT_PATH
    output_path = write_trace_export(output_path=output_path, limit=10)
    print(f"Exported trace to {output_path}")


if __name__ == "__main__":
    main()
