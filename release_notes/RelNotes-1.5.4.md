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
