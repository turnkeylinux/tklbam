from typing import Optional
from dataclasses import dataclass


@dataclass
class DBLimits:
    """ class to contain DB related TKLBAM "limit" data

    Note that as of tklbam3 this slightly deviates from original tklbam
    behavior. Previously self.d keys could be str (db) or tuple[str, str]
    (tuple[db, tbl]). It now must be a tuple. If no table, it will be an
    empty string.
    """

    limits: Optional[list[str]] = None
    default: bool = True
    databases: Optional[list[str]] = None
    tables: Optional[list[tuple[str, str]]] = None

    def __post_init__(self) -> None:
        if self.databases is None:
            self.databases = []
        if self.tables is None:
            self.tables = []

        self.d: dict[tuple[str, str], bool | str] = {}
        if self.limits:
            for limit in self.limits:
                database = ''
                table = ''
                if limit[0] == '-':
                    limit = limit[1:]
                    sign = False
                else:
                    sign = True
                    self.default = False

                if '/' in limit:
                    database, table = limit.split('/')
                    self.tables.append((database, table))
                # XXX whilst below seems logical to me (Jed) it seems to be
                # inconsistent with the previous behavior
                #else:
                #    database = limit

                if database:
                    if sign:
                        self.databases.append(database)
                    self.d[(database, table)] = sign

    def __contains__(self, val: str | tuple[str, str]) -> bool:
        """Tests if <val> is within the defined Database limits

        <val> can be:

            1) a (database, table) tuple
            2) a database string
            3) database/table
        """
        database: str
        table = ''
        if isinstance(val, str):
            if '/' in val:
                database, table = val.split('/')
            else:
                database = val
        elif isinstance(val, tuple):
            database, table = val
        else:
            raise ValueError(f'invalid input type: {val}')

        limit = (database, table)
        if limit in self.d.keys():
            return bool(self.d[limit])
        else:
            return self.default

    def __getitem__(self, database_limit: str) -> list[tuple[str, bool | str]]:
        table_limits = []
        assert self.tables is not None
        for database, table in self.tables:
            if database != database_limit:
                continue

            sign = self.d[(database, table)]
            table_limits.append((table, sign))

        return table_limits
