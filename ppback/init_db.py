
import os
from typing import List

from pydantic import BaseModel

from db.dbfuncs import add_users, create_convo
from ppback.db.ppdb_schemas import Base, Conv, ConvPrivacyMembers, UserInfo
from ppback.db.db_connect import create_session
from secu.sec_utils import get_hashed_password


def create_starting_point_db(session,chat_stream_names):

    users = [["fanf","fanf"],["ted","ted"]]
    users = add_users(session,users)

    create_convo(session,"General",users)
    create_convo(session,"About",users)
    create_convo(session,"Test",users)
    create_convo(session,"Random",users)

    # testing werid stuff for the ui 
    create_convo(session,"Test Space",users) 
    create_convo(session,"Te\nst Space",users) 
    

session,engine = create_session(os.getenv("DB_SESSION_STR","sqlite:///devdb/chat_database.db"))
Base.metadata.create_all(engine)
create_starting_point_db(session,chat_stream_names=["live_chat","second_chat","yet_another_chat"])