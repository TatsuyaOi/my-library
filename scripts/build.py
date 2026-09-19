"""One command for public output and optional isolated draft preview."""
import argparse
from build_library import build
from prepare_pages import prepare, ROOT

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preview', action='store_true', help='Also generate local _preview with drafts')
    args = parser.parse_args()
    try:
        build()
        print(prepare(ROOT))
        if args.preview:
            print(prepare(ROOT, preview=True))
    except (ValueError, KeyError, OSError, ImportError) as exc:
        parser.exit(1, f'Learning build error: {exc}\n')
