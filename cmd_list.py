#!/usr/bin/python
"""
List backup records
"""
import hub
from registry import registry

def main():
    hb = hub.Backups(registry.sub_apikey)
    hbrs = hb.list_backups()

    for hbr in hbrs:
        print "%s" % hbr.backup_id

if __name__ == "__main__":
    main()
