#!/usr/bin/python
"""
List backup records
"""
import hub
from registry import registry

def main():
    hb = hub.Backups(registry.sub_apikey)
    hbrs = hb.list_backups()

    print "# ID         Created     Updated    Size (GB)  Label"
    for hbr in hbrs:
        print "%s %s  %-10s %-8.1f   %s" % (hbr.backup_id,
                                       hbr.created.strftime("%Y-%m-%d"),
                                       hbr.updated.strftime("%Y-%m-%d") if hbr.updated else "-",
                                       hbr.size / 1024.0,
                                       hbr.label)

if __name__ == "__main__":
    main()
