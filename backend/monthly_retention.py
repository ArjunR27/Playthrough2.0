from datetime import datetime, timezone
import os


def _env_bool(name, default=False):
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


# PostgREST reports PGRST202 when the function is absent from the schema cache;
# Postgres reports 42883 (undefined_function) when no matching signature exists.
_MISSING_FUNCTION_MARKERS = ("PGRST202", "42883")


def _is_missing_function(exc):
    code = getattr(exc, "code", None)
    if code in _MISSING_FUNCTION_MARKERS:
        return True
    return any(marker in str(exc) for marker in _MISSING_FUNCTION_MARKERS)


def run_lastfm_monthly_retention(supabase):
    """Run the Postgres-side Last.fm monthly retention job if installed."""
    if _env_bool("LASTFM_MONTHLY_RETENTION_DISABLED", False):
        print("[retention][lastfm] Monthly retention disabled by environment")
        return []

    month_key = datetime.now(timezone.utc).strftime("%Y-%m")
    dry_run = not _env_bool("LASTFM_MONTHLY_RETENTION_APPLY", False)
    dry_run = _env_bool("LASTFM_MONTHLY_RETENTION_DRY_RUN", dry_run)

    try:
        resp = supabase.rpc(
            "run_lastfm_monthly_retention",
            {
                "p_month_key": month_key,
                "p_dry_run": dry_run,
            },
        ).execute()
    except Exception as exc:
        if _is_missing_function(exc):
            print(
                "[retention][lastfm] Skipping monthly retention; "
                f"install SQL migration first. error={exc}"
            )
        else:
            print(
                "[retention][lastfm] ERROR: monthly retention failed "
                f"(month={month_key}, mode={'dry-run' if dry_run else 'apply'}): "
                f"{type(exc).__name__}: {exc}"
            )
        return []

    rows = resp.data or []
    mode = "dry-run" if dry_run else "apply"
    if not rows:
        print(f"[retention][lastfm] No retention actions returned ({mode})")
        return rows

    print(f"[retention][lastfm] Monthly retention summary ({mode}, month={month_key})")
    for row in rows:
        table_name = row.get("table_name")
        action = row.get("action")
        row_count = row.get("row_count")
        print(f"[retention][lastfm] {table_name}: {action} rows={row_count}")

    return rows
