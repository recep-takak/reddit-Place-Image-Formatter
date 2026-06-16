from __future__ import annotations

import argparse
from pathlib import Path

from formatter import FormatOptions, InvalidInputError, UnsupportedFormatError, format_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Format media for the r/place palette.")
    parser.add_argument("input", type=Path, help="Image, GIF, or video to format")
    parser.add_argument("width", type=int, help="Output width in logical pixels (1-1000)")
    parser.add_argument("-o", "--output", type=Path, help="Output path")
    parser.add_argument("--no-grid", action="store_true", help="Do not draw the pixel grid")
    parser.add_argument("--scale", type=int, default=10, help="Display scale per logical pixel")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output = args.output or Path.cwd() / f"pixel_{args.input.stem}{args.input.suffix}"
    try:
        result = format_file(
            args.input,
            output,
            FormatOptions(width=args.width, grid=not args.no_grid, scale=args.scale),
        )
    except (InvalidInputError, UnsupportedFormatError) as exc:
        build_parser().error(str(exc))
    print(result.output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
