class DBLimits:
    def __init__(self, limits):
        self.default = True
        self.databases = []
        self.tables = []

        d = {}
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

    def __contains__(self, val):
        """Tests if <val> is within the defined Database limits

        <val> can be:

            1) a (database, table) tuple
            2) a database string
            3) database/table

        """
        if '/' in val:
            database, table = val.split('/')
            val = (database, table)

        if isinstance(val, type(())):
            database, table = val
            if (database, table) in self.d:
                return self.d[(database, table)]

            if database in self.d:
                return self.d[database]

            return self.default

        else:
            database = val
            if database in self.d:
                return self.d[database]

            if database in self.databases:
                return True

            return self.default

    def __getitem__(self, database_limit):
        table_limits = []
        for database, table in self.tables:
            if database != database_limit:
                continue

            sign = self.d[(database, table)]
            table_limits.append((table, sign))

        return table_limits
