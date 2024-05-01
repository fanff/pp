
import json
import websockets
import httpx

class PPC():
    def __init__(self,apihost="http://localhost:8000/",wshost="ws://localhost:8000/"):
        self.host = apihost

        self.wshost = wshost
        self.token = None
        self.headers={"accept":"application/json"}


    async def login(self,user_id:str,passwd:str):
        h = dict(self.headers.copy())
        h["Content-Type"] = "application/x-www-form-urlencoded"
        async with httpx.AsyncClient() as client:
            try:
                r = await client.post(self.host + "token",headers=h,
                                      data={"username":user_id,"password":passwd})
                if r.status_code == 200:
                    return r.json()
                else:
                    return None
            except httpx.NetworkError:
                return None

    def header_with_token(self):
        t = self.token["access_token"]

        h = self.headers.copy()
        h["Authorization"] = f"Bearer {t}"
        
        return h
    def setup_token(self, d):
        self.token = d

    async def simple_get_query(self,endpoint:str,):
        async with httpx.AsyncClient() as client:
            try:
                r = await client.get(self.host + endpoint,headers=self.header_with_token())
                if r.status_code == 200:
                    return r.json()
                else:
                    return None
            except httpx.NetworkError:
                return None
    

    async def conv(self):
        return await self.simple_get_query("conv")
    async def convid(self,id):
        return await self.simple_get_query(f"conv/{id}")
    async def users(self):
        return await self.simple_get_query(f"users")
    

    async def usermsg(self,conversation_id,message):
        async with httpx.AsyncClient() as client:
            try:
                r = await client.post(self.host + "usermsg",
                                      headers=self.header_with_token(),
                                      json={"content":message,"conversation_id":conversation_id})
                if r.status_code == 200:
                    return r.json()
                else:
                    return None
            except httpx.NetworkError:
                return None
    

    async def ws_client_connection_the_rightversion(self,awaitable_loop):
        h = self.header_with_token()
        async with websockets.connect(self.wshost+"ws",extra_headers=h) as websocket:
            #websocket.send({"user_id":user_id,"passwd":passwd,"op":"login"})
            await awaitable_loop(websocket)
            #await self.ws_loop(websocket)

    async def ws_client_connection(self,awaitable_loop):
        uri = self.wshost+"ws"
        thetoken = self.token["access_token"]
        h = self.header_with_token()
        async with websockets.connect(uri) as websocket:
            await websocket.send(json.dumps(["somestuff",f"Authorization: Bearer {thetoken}"]).encode("utf-8"))
            await awaitable_loop(websocket)
            #await self.ws_loop(websocket)


async def ws_loop(ws:websockets.WebSocketClientProtocol):
    while True:
        try:
            msg = await ws.recv()
            print(f"Received: {msg}")
        except Exception as e:
            raise e

async def main():
    """ here is a sequence of API usage :"""

    # fanf get a client 
    c = PPC()
    # do login
    l2 = await c.login("fanf","fanf")
    print(l2)

    # setup its token to its client
    c.setup_token(l2)
    # now can read all users
    users = await c.users()
    print(users)
    # and can read all conversations
    cl = await c.conv()
    print(cl)

    # and read content
    cld = await c.convid(1)
    print(cld)

    # also subscribe to the ws connection to listen to new message 
    task = asyncio.create_task(c.ws_client_connection(ws_loop))
    await asyncio.sleep(3)

    # check if the task has failed (it should not)
    if task.done():
        task.result()
        quit()

    # ted get aclient
    print("tedenter") 
    ct = PPC()
    # and does login
    l2 = await c.login("ted","ted")
    ct.setup_token(l2)
    # ted send a message to the conversation 1 (with fanf)
    res = await ct.usermsg(1,"hello")
    print("message sent",res)


    # keep an infinite loop running, a CTRL+C with hang this 
    while not task.done():
        await asyncio.sleep(1)

if __name__=="__main__":
    import asyncio

    asyncio.run(main())
