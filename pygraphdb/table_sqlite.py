from table_sql import PlainSQL


class SQLiteMem(PlainSQL):
    """
        In-memory version of SQLite database.
    """
    __is_concurrent__ = False


class SQLite(PlainSQL):
    """
        SQLite may be the fastest option for tiny databases 
        under 20 Mb. It's write aplification is huge. 
        Bulk inserting 250 Mb unweighted undirected graph 
        will write ~200 Gb of data to disk.
        The resulting file size will be ~1 Gb.

        https://www.sqlite.org/faq.html#q19
        https://stackoverflow.com/a/6533930/2766161
    """
    __is_concurrent__ = False

    def __init__(self, url):
        PlainSQL.__init__(self, url)
        self.set_pragmas_on_first_launch()

    def set_pragmas_on_first_launch(self):
        if self.count_edges() > 0:
            return
        # https://stackoverflow.com/a/6533930/2766161
        pragmas = [
            'PRAGMA main.page_size=4096;',
            'PRAGMA main.cache_size=10000;',
            'PRAGMA main.locking_mode=EXCLUSIVE;',
            'PRAGMA main.journal_mode=WAL;',
            'PRAGMA main.temp_store=MEMORY;',
        ]
        for p in pragmas:
            self.session.execute(p)
            self.session.commit()