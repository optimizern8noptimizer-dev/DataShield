# DataShield BY v2.4.2 Auth Hotfix

- Added DS_BOOTSTRAP_FORCE_SYNC support.
- Existing bootstrap admin is now updated on startup when DS_BOOTSTRAP_FORCE_SYNC=1.
- Username/password are trimmed before sync.
- Use with deleted datashield_control.db for clean reset if needed.
