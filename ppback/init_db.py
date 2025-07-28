import os

from ppback.db.db_connect import create_session
from ppback.db.dbfuncs import add_users, create_convo
from ppback.db.ppdb_schemas import Base


def create_starting_point_db(session):

    users = [["fanf", "fanf"], ["ted", "ted"]]
    users = add_users(session, users)

    create_convo(session, "General", users)
    create_convo(session, "About", users)
    create_convo(session, "Test", users)
    create_convo(session, "Random", users)

    # testing werid stuff for the ui
    create_convo(session, "Test Space", users)
    create_convo(session, "Te\nst Space", users)


def init_db(session, engine):
    Base.metadata.create_all(engine)
