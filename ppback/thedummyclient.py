import json
import time

import httpx
import websockets


class PPC:
    def __init__(self, apihost="http://localhost:8000/", wshost="ws://localhost:8000/"):
        self.host = apihost

        self.wshost = wshost
        self.token = None
        self.headers = {"accept": "application/json"}

    async def login(self, user_id: str, passwd: str):
        h = dict(self.headers.copy())
        h["Content-Type"] = "application/x-www-form-urlencoded"
        async with httpx.AsyncClient() as client:
            try:
                r = await client.post(
                    self.host + "token",
                    headers=h,
                    data={"username": user_id, "password": passwd},
                )
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

    async def simple_get_query(
        self,
        endpoint: str,
    ):
        async with httpx.AsyncClient() as client:
            try:
                r = await client.get(
                    self.host + endpoint, headers=self.header_with_token()
                )
                if r.status_code == 200:
                    return r.json()
                else:
                    return None
            except httpx.NetworkError:
                return None

    async def conv(self):
        return await self.simple_get_query("conv")

    async def convid(self, convid):
        return await self.simple_get_query(f"conv/{convid}")

    async def users(self):
        return await self.simple_get_query("users")

    async def usermsg(self, conversation_id, message):
        async with httpx.AsyncClient() as client:
            try:
                r = await client.post(
                    self.host + "usermsg",
                    headers=self.header_with_token(),
                    json={"content": message, "conversation_id": conversation_id},
                )
                if r.status_code == 200:
                    return r.json()
                else:
                    return None
            except httpx.NetworkError:
                return None

    async def ws_client_connection_the_rightversion(self, awaitable_loop):
        h = self.header_with_token()
        async with websockets.connect(self.wshost + "ws", extra_headers=h) as websocket:
            # websocket.send({"user_id":user_id,"passwd":passwd,"op":"login"})
            await awaitable_loop(websocket)
            # await self.ws_loop(websocket)

    async def ws_client_connection(self, awaitable_loop,*args,**kwargs):
        uri = self.wshost + "ws"
        thetoken = self.token["access_token"]
        async with websockets.connect(uri) as websocket:
            await websocket.send(
                json.dumps(["somestuff", f"Authorization: Bearer {thetoken}"]).encode(
                    "utf-8"
                )
            )
            await awaitable_loop(websocket,*args,**kwargs)
            # await self.ws_loop(websocket)


async def ws_loop(ws: websockets.WebSocketClientProtocol):
    while True:
        try:
            msg = await ws.recv()
            print(f"Received: {msg}")
        except Exception as e:
            raise e


async def main():
    """here is a sequence of API usage :"""

    # fanf get a client
    c = PPC()
    # do login
    l2 = await c.login("fanf", "fanf")
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
    print("ted enter the room")
    ct = PPC()
    # and does login
    l2 = await c.login("ted", "ted")
    ct.setup_token(l2)
    # ted send a message to the conversation 1 (with fanf)
    res = await ct.usermsg(1, "hello")
    print("message sent", res)

    # keep an infinite loop running, a CTRL+C with hang this
    while not task.done():
        await asyncio.sleep(1)

async def little_benchmark():
    messagebatch = 100
    count_per_batch = 10

    conversationchannel = 2
    # fanf get a client
    fanf = PPC()
    fanf.setup_token(await fanf.login("fanf", "fanf"))
    
    async def fanfloop(ws: websockets.WebSocketClientProtocol,count):
        msg_counter=count
        while True:
            msg = await ws.recv()
            m = json.loads(msg)

            print("received",m)
            msg_counter-=1
            if msg_counter==0:
                if m["content"]=="hello":
                    break
                else:
                    print("error")
                    break

    task = asyncio.create_task(fanf.ws_client_connection(fanfloop,messagebatch))

    # ted will send message to fanf
    ted = PPC()
    ted.setup_token(await ted.login("ted", "ted"))

    start_time = time.time()
    
    # pushing message in batchs 
    # prepare division batch
    batch_count = (messagebatch-1)//count_per_batch

    remaining = (messagebatch-1) - batch_count*count_per_batch
    
    for i in ([count_per_batch]*batch_count + [remaining]):
        print("sending batch ",i)
        await asyncio.gather(*[ted.usermsg(conversationchannel, "some randome string "*3) for _ in range(i)])

    await ted.usermsg(conversationchannel, "hello")

    print("ted sent all messages")
    while not task.done():
        await asyncio.sleep(.1)
    end_time = time.time()
    print("done benchmark :)")
    dur = end_time-start_time
    print(f"elapsed time : {dur:.2f} sec, for {messagebatch} messages. ({messagebatch/dur:.2f} msg/sec)")


if __name__ == "__main__":
    import asyncio

    asyncio.run(little_benchmark())
