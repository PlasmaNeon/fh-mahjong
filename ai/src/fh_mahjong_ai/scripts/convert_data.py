"""Convert transition datasets between supported storage formats."""
from __future__ import annotations

import argparse
from pathlib import Path

from fh_mahjong_ai.storage import SHARDED_TRANSITIONS_MANIFEST, iter_transitions_jsonl, read_transitions, write_transitions_npz_shards


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert Mahjong transition data")
    parser.add_argument("--input", type=Path, required=True, help="Input JSONL file or sharded dataset directory")
    parser.add_argument("--output-dir", type=Path, required=True, help="Output directory for NumPy transition shards")
    parser.add_argument("--shard-size", type=int, default=50_000, help="Transitions per output shard")
    parser.add_argument("--compressed", action="store_true", help="Use compressed .npz shards")
    args = parser.parse_args()

    if args.input.is_file() and args.input.name != SHARDED_TRANSITIONS_MANIFEST:
        transitions = iter_transitions_jsonl(args.input)
    else:
        transitions = read_transitions(args.input)
    manifest = write_transitions_npz_shards(
        args.output_dir,
        transitions,
        shard_size=args.shard_size,
        compressed=args.compressed,
    )
    print(
        f"Converted {manifest['transitions']} transitions into "
        f"{len(manifest['shards'])} shard(s) at {args.output_dir}"
    )


if __name__ == "__main__":
    main()
