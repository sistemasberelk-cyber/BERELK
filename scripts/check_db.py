from sqlmodel import create_engine, inspect
import os

# Try both locations to be sure
paths = ["nexpos.db", "database/nexpos.db"]

for p in paths:
    if os.path.exists(p):
        print(f" Checking DB at: {p}")
        engine = create_engine(f"sqlite:///{p}")
        insp = inspect(engine)
        for table in insp.get_table_names():
            print(f"Table: {table}")
            columns = [c['name'] for c in insp.get_columns(table)]
            print(f"  Columns: {columns}")
    else:
        print(f" DB not found at: {p}")
