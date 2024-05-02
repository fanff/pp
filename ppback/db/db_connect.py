from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def create_session(dbstr):
    # Create an engine that stores data in the local directory's
    # chat_database.db file.
    engine = create_engine(dbstr)

    # Bind the engine to the metadata of the Base class so that the
    # declaratives can be accessed through a DBSession instance
    dbession = sessionmaker(bind=engine)
    session = dbession()
    return session, engine


def get_session(dbstr):
    return sessionmaker(autoflush=True, bind=create_engine(dbstr))
