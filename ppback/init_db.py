import os

from ppback.db.db_connect import create_session
from ppback.db.dbfuncs import add_users, create_convo
from ppback.db.ppdb_schemas import Base


def create_starting_point_db(session):

    users = [("admin", "admin"), ("user", "user")]
    users = add_users(session, users)

    create_convo(session, "General", users)
    create_convo(session, "Random", users)
    create_convo(session, "About", users)


def init_db(session, engine):
    Base.metadata.create_all(engine)


if __name__ == "__main__":
    from . import main

    print("Initializing DB at " + main.DB_SESSION_STR)
    session, engine = create_session(main.DB_SESSION_STR)
    init_db(session, engine)
    create_starting_point_db(session)
