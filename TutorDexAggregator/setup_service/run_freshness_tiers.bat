@echo off
REM Runs freshness tier updates (hourly scheduled job).
REM Expects Supabase env vars in `TutorDexAggregator/.env`.

cd /D d:\TutorDex\TutorDexAggregator

REM Tier thresholds:
REM - red after 7 days (168h), but do NOT close yet
REM - close after 14 days (336h)

where python >nul 2>&1
if %errorlevel% equ 0 (
    python update_freshness_tiers.py --expire-action none --red-hours 168
    python update_freshness_tiers.py --expire-action closed --red-hours 336
) else (
    py -3 update_freshness_tiers.py --expire-action none --red-hours 168
    py -3 update_freshness_tiers.py --expire-action closed --red-hours 336
)

