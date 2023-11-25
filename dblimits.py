from typing import Optional

class DBLimits:
    def __init__(self, limits: Optional[list[str]]):
        self.default = True
        self.databases = []
        self.tables = []

        d: dict[str|tuple[str, str], bool|str] = {}
        if limits:
            for limit in limits:
                if limit[0] == '-':
                    limit = limit[1:]
                    sign = False
                else:
                    sign = True
                    self.default = False

                if '/' in limit:
                    database, table = limit.split('/')
                    self.tables.append((database, table))

                    d[(database, table)] = sign
                    if sign:
                        self.databases.append(database)
                else:
                    database = limit
                    d[database] = sign

        self.d = d

    def __contains__(self, val: str) -> bool:
        """Tests if <val> is within the defined Database limits

        <val> can be:

            1) a (database, table) tuple
            2) a database string
            3) database/table

        """
        val_: tuple[str, ...]
        if isinstance(val, str):
            if '/' in val:
                database, table = val.split('/')
                val_ = (database, table)
            else:
                val_ = tuple(val)
        elif isinstance(val, tuple):
            val_ = val
        else:
            raise ValueError(f'invalid input type: {val}')

        if len(val_) == 2:
            database, table = val_
            if (database, table) in self.d:
                return bool(self.d[(database, table)])

            if database in self.d:
                return bool(self.d[database])

            return self.default

        elif  len(val_) == 1:
            database = str(*val_)
            if database in self.d:
                return bool(self.d[database])

            if database in self.databases:
                return True

            return self.default
        else:
            raise ValueError(f'invalid DB limit: {val}')

    def __getitem__(self, database_limit: str) -> list[tuple[str, bool|str]]:
        table_limits = []
        for database, table in self.tables:
            if database != database_limit:
                continue

            sign = self.d[(database, table)]
            table_limits.append((table, sign))

        return table_limits
