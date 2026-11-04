"""Use an extension-capable SQLite driver on macOS Python builds that need it."""
import sqlite3
import sys

if sys.platform == 'darwin' and not hasattr(sqlite3.Connection, 'enable_load_extension'):
    import pysqlite3
    sys.modules['sqlite3'] = pysqlite3
    sys.modules['sqlite3.dbapi2'] = pysqlite3.dbapi2
