"""Exercise the actual photo Games page (compatibility entrypoint)."""
import argparse
from pathlib import Path

if __package__:
    from .games_triple_check import walkthrough
else:
    from games_triple_check import walkthrough


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('_ci_temp'))
    args = parser.parse_args()
    walkthrough(args.output.resolve())
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
