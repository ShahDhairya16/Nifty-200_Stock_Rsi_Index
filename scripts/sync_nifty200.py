import sys
from pathlib import Path

# Add workspace root to python path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.services.universe_update_service import UniverseUpdateService

def main():
    print("\n" + "=" * 60)
    print("      CNX 200 RSI Dashboard - Stock Universe Synchronization     ")
    print("=" * 60 + "\n")

    print("Starting NIFTY 200 Universe Sync...\n")
    print("Fetching latest NIFTY 200 constituents...\n")

    summary = UniverseUpdateService.auto_update(
        force=True,
        backfill_new=True,
        recompute_rsi=True,
    )

    if summary.get("errors"):
        print(f"[WARN] Universe sync reported: {summary['errors']}")

    universe = summary.get("universe_summary") or {}
    print(f"Status: {summary.get('status')}\n")
    print(f"Fetched: {summary.get('symbol_count', universe.get('total_fetched', 0))} stocks\n")
    print(f"New Stocks: {len(summary.get('added', []))} {summary.get('added', [])}")
    print(f"Removed Stocks: {len(summary.get('removed', []))} {summary.get('removed', [])}")
    print(f"Snapshot Updated: {summary.get('snapshot_updated', False)}")
    print(f"RSI Recomputed: {summary.get('rsi_recomputed', False)}\n")

    if summary.get("status") == "FAILED":
        sys.exit(1)

    print("Sync completed successfully.\n")

if __name__ == "__main__":
    main()
