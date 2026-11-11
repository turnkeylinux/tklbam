## v1.5.4 Release notes

* Bugfixes:
    - Restore TKLBAM backup and restore support for Hub records that use the
      default US East S3 endpoint.
    - Stop backups when a running database cannot be exported, including
      failures hidden by a successful downstream archive command.
    - Restore verification of signed appliance profile hooks using a packaged
      keyring dedicated to backups. Missing or invalid signatures now stop the
      operation instead of silently omitting application data. Verified with
      actual OpenLDAP configuration and account backup, mutation and restore.

* Hub integration:
    - Initialize through the existing server connection on first backup, or with `tklbam-init`. Offers browser approval when linking is needed.
    - Preserve existing credentials, encryption keys and backup history when upgrading. Use `--force` to replace authorization after validating the replacement.
    - Report incomplete AWS and backup setup when a backup is requested.
    - Keep scheduled jobs quiet until backup initialization succeeds.
