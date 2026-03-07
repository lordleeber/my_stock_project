from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Move current strategies/ contents into strategies_history/<idea_name>.")
    parser.add_argument("idea_name", help="example: idea_a03")
    return parser.parse_args()


def iter_move_entries(strategies_dir: Path) -> list[Path]:
    entries = []
    for path in sorted(strategies_dir.iterdir()):
        if path.name in {"__pycache__", ".DS_Store", "deprecated"}:
            continue
        entries.append(path)
    return entries


def main() -> None:
    args = parse_args()
    repo_root = Path(__file__).resolve().parent.parent
    strategies_dir = repo_root / "strategies"
    history_root = repo_root / "strategies_history"
    target_dir = history_root / args.idea_name

    if not strategies_dir.exists():
        raise FileNotFoundError(f"strategies directory not found: {strategies_dir}")
    if target_dir.exists():
        raise FileExistsError(f"target history directory already exists: {target_dir}")

    entries = iter_move_entries(strategies_dir)
    if not entries:
        raise RuntimeError(f"no movable files found in: {strategies_dir}")

    target_dir.mkdir(parents=True, exist_ok=False)

    print(f"Move strategies/* -> {target_dir}")
    for src in entries:
        dst = target_dir / src.name
        print(f"- move {src.relative_to(repo_root)} -> {dst.relative_to(repo_root)}")
        shutil.move(str(src), str(dst))

    print("move_to_history completed")
    print(f"- target: {target_dir}")
    print(f"- moved_count: {len(entries)}")


if __name__ == "__main__":
    main()
