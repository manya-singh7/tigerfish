#!/usr/bin/env python3
"""Build TigerFish's free batch corpus and report.

Examples:
  python scripts/build_corpus.py discover --limit 90
  python scripts/build_corpus.py check --limit 90
  python scripts/build_corpus.py run --limit 90

``run`` uses Tavily Map/Crawl for discovery, downloads at most 90 English PDFs,
then runs only regexes and cached GBIF checks.  It never imports the model
pipeline and never uses NEBIUS_API_KEY.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tigerfish import batch  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=("discover", "download", "check", "run", "refresh-baselines")
    )
    parser.add_argument("--limit", type=int, default=batch.DEFAULT_MAX_REPORTS)
    parser.add_argument("--max-credits", type=int, default=batch.MAX_TAVILY_CREDITS)
    parser.add_argument(
        "--download-missing",
        action="store_true",
        help="refresh-baselines: fetch saved source PDFs, verifying their original hashes",
    )
    args = parser.parse_args()

    # load_dotenv is optional for this script; an explicitly exported key wins.
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
    except ImportError:
        pass

    if args.command == "refresh-baselines":
        summary = batch.refresh_baselines(download_missing=args.download_missing)
    elif args.command in ("discover", "run"):
        if not os.getenv("TAVILY_API_KEY"):
            parser.error("TAVILY_API_KEY is missing; put only that key in .env")
        candidates, stats = batch.discover_candidates(max_credits=args.max_credits)
        print(
            f"Tavily discovered {len(candidates)} PDF candidates; {stats.credits:g} credits used"
        )
        index = batch.download_candidates(candidates, limit=args.limit)
        print(f"Corpus now contains {index.get('downloaded', 0)} PDFs")
        if args.command == "discover":
            batch.run_batch(index, max_reports=args.limit, tavily=stats.as_dict())
            return 0
        summary = batch.run_batch(index, max_reports=args.limit, tavily=stats.as_dict())
    elif args.command == "download":
        parser.error(
            "download is resumable through the discover/run command; discovery must use Tavily Map/Crawl"
        )
    else:
        summary = batch.run_batch(max_reports=args.limit)

    print(
        f"Processed {summary['reports_processed']} reports; flags: {summary['flag_counts']}"
    )
    print(f"Wrote {batch.SUMMARY_JSON} and {batch.SUMMARY_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
