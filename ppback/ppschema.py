

from typing import List, Optional
from pydantic import BaseModel



# web socket simple schemas
class MessageWS(BaseModel):
    content:str
    originator:int
    convo_id:int
              