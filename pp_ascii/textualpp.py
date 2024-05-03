#!/usr/bin/env python3

import datetime
import json
import os
from types import NoneType
from typing import List
import uuid

import websockets

from textual.app import App
from textual import events
from textual.app import App, ComposeResult
from textual.widgets import Welcome,Button,TextArea,Static,Label,RichLog,ListView,Tree,ContentSwitcher, DataTable, Markdown
from textual.widgets import Footer, Label, ListItem, ListView,Input
from textual.widgets import Label, Rule
from textual.widgets import Footer, Label, Markdown, TabbedContent, TabPane

from textual.widgets._tree import TreeNode
import asyncio
from textual.containers import Horizontal, ScrollableContainer, Vertical
from time import time
from textual.reactive import reactive


from ppback.ppschema import MessageWS
from ppback.thedummyclient import PPC



class MessageInputBox(Static):
    def compose(self) -> ComposeResult:
        yield TextArea(classes="messageinputarea",id="messageinputarea")
        yield Button("Send",classes="sendmessagebutton")

class CustomTA(TextArea):

    def on_focus(self) -> None:
        self.add_class("selected_msg")
    def _on_blur(self, event: events.Blur) -> None:
        self.remove_class("selected_msg")


class BorderTitledMsg(Static):
    can_focus=False
    def compose(self) -> ComposeResult:
        ta = CustomTA(classes="message_text_area",read_only=True)
        ta.cursor_blink=False
        yield ta
    def on_focus(self) -> None:
        pass#self.add_class("selected_msg")
    def _on_blur(self, event: events.Blur) -> None:
        pass#self.remove_class("selected_msg")



        #with Vertical():
        #    with Horizontal(classes="msg_header"):
        #        with Horizontal(classes="msg_header_left"):
        #            yield Label("")
        #            yield Label("12:12")
        #            yield Label(" ")
        #            yield Label("Fanff")
        #        with Horizontal(classes="msg_header_right"):
        #            yield Label("",name="msg_header_right_0")
        #            yield Label("12:12",name="msg_header_right_1")
        #            yield Label(" ",name="msg_header_right_2")
        #            yield Label("Fanff",name="msg_header_right_3")
        #    
        #    with Horizontal(classes="msg_footer"):
        #        with Horizontal(classes="msg_footer_left"):
        #            yield Label("↵")
        #            yield Label("12:12")
        #            yield Label(" ")
        #            yield Label("Fanff")
        #        with Horizontal(classes="msg_footer_right"):
        #            yield Label("")
        #            yield Label("12:12")
        #            yield Label(" ")
        #            yield Label("Fanff")






class Convo(ScrollableContainer):
    can_focus=True
    can_focus_children=True

    # scrolling timer
    is_timer_running = False

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.current_selected_idx = -1

    def timer_scroll_end(self):
        if not self.is_timer_running:
            def do_scroll_():
                self.is_timer_running = False
                self.scroll_end()
            self.is_timer_running = True
            self.set_timer(0.1,do_scroll_)

    async def append_msg(self,msg, auto_scroll=True):
        await self.mount(msg)
        self.current_selected_idx = len(self.children)-1

        if auto_scroll:
            self.timer_scroll_end()

    async def append_other_msg(self,msg_id,content,sendernick,timestr,auto_scroll=True):
        other_msg =OtherMsg("")
        # append the message to the convo
        await self.append_msg(other_msg,auto_scroll=False)

        other_msg.msg_id = msg_id
        other_msg.tree_id = None

        other_msg.username = sendernick
        other_msg.msg_content =content
        other_msg.msg_time = timestr
        if auto_scroll:
            self.timer_scroll_end()

    async def append_user_msg(self,msg_id,content,sendernick,timestr,auto_scroll=True):
        m =UserMsg()
        await self.append_msg(m,auto_scroll=False)
        m.msg_content = content
        m.username = sendernick
        m.msg_time = timestr
        if auto_scroll:
            self.timer_scroll_end()


    #def get_the_message_at_curr_idx(self):
    #    return self.children[self.current_selected_idx]
        
    #def select_idx(self,idx):
    #    if idx < len(self.children) and idx >= 0:
    #        self.children[idx].add_class("selected_msg")
    #        self.scroll_to_widget(self.children[idx])
#
    #def unselect_idx(self,idx):
    #    if idx < len(self.children) and idx >= 0:
    #        self.children[idx].remove_class("selected_msg")

    #def on_focus(self) -> None:
#
    #    if self.current_selected_idx != -1:
    #        self.select_idx(self.current_selected_idx)
    #    else:
    #        self.current_selected_idx = len(self.children)-1
    #        self.select_idx(self.current_selected_idx)

    #def _on_blur(self, event: events.Blur) -> None:
    #    self.unselect_idx(self.current_selected_idx)
    #    return super()._on_blur(event)

    #async def on_key(self, event: events.Key) -> None:
    #    if len(self.children) >= 1:
    #        if event.key == "j":
    #            self.unselect_idx(self.current_selected_idx)
    #            self.current_selected_idx = 0 if len(self.children)-1==self.current_selected_idx else self.current_selected_idx+1
    #            self.select_idx(self.current_selected_idx)
    #        elif event.key == "k":
    #            self.unselect_idx(self.current_selected_idx)
    #            self.current_selected_idx = len(self.children)-1 if self.current_selected_idx==0 else self.current_selected_idx-1
    #            self.select_idx(self.current_selected_idx)

def set_tree_value(node:TreeNode, log_operation:str, path_parts:List[str], value):

    
    # Base case: if the path is empty, we have reached the target node
    if not path_parts:
        if log_operation == "add":
            # node.add_leaf(f"{type(value)} -> {value}") 
            if isinstance(value,dict):
                for k,v in value.items():
                    set_tree_value(node, log_operation, [k], v)
            elif isinstance(value,list):
                for idx,v in enumerate(value):
                    set_tree_value(node, log_operation, [str(idx)], v)
            elif isinstance(value,str):
                node.add_leaf(f"{value}")
            elif isinstance(value,NoneType):
                node.add_leaf(f"{value}")
            else:
                #node.label = f"{type(value)} -> {value}"
                node.add_leaf(f"{type(value)} -> {value}") 
        elif log_operation == "replace":
            if isinstance(value,dict):
                for k,v in value.items():
                    set_tree_value(node, log_operation, [k], v)
            elif isinstance(value,list):
                
                for idx,v in enumerate(value):
                    set_tree_value(node, log_operation, [str(idx)], v)
                    #node.add_leaf(f"{idx}")
            else:
                node.label = f"{node.label}: {value}"
        
        return

    # Recursive case: traverse the path
    part = path_parts.pop(0)  # Get the next part of the path
    for c in node.children:
        if str(c.label) == part:
            set_tree_value(c, log_operation,path_parts, value)
            return
        
    # If the part is not already a child of the current node, create a new node
    c = node.add(part,expand=True)
    # Recur into the child node
    set_tree_value(c, log_operation,path_parts, value)


def random_widget_id()->str:
    return "pp"+uuid.uuid4().hex

class DiscussionsWidgets(Static):
    initial_discussion_id:str = None
    def compose(self) :
        self.initial_discussion_id = random_widget_id()
        with ContentSwitcher(initial=self.initial_discussion_id,classes="discussion_switcher"):  
            pass #yield DiscussionWidget(*aaaa, classes="convo",id=self.switcher_conv_id)
            yield Label("Welcome message :) ",id=self.initial_discussion_id)

class DiscussionWidget(Static):
    """It has all the necessarry to discuss."""
    can_focus=False
    queueinbound:asyncio.Queue = None 
    aqueueoutput:asyncio.Queue  = None  
    switcher_conv_id:str = None
    switcher_ids: List[str] = []
    task: asyncio.Task = None
    task2: asyncio.Task = None

    user_nick_name = reactive("Fanf")
    conv_id:int = reactive(-1)


    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.queueinbound = asyncio.Queue()
        self.aqueueoutput = asyncio.Queue()
        self.switcher_conv_id:str = "pp"+uuid.uuid4().hex

        self.switcher_ids = [self.switcher_conv_id]
        
        #self.task = asyncio.create_task(manage_agent(self.queueinbound, None, self.aqueueoutput))
        self.task2:asyncio.Task = asyncio.create_task(self.update_response_loop(self.aqueueoutput))
        self.set_interval(0.1,self.check_asynctask_status)      
        
    def check_asynctask_status(self):
        # if task is done it is actually a problem; 
        # if task is not done, it is ok.
        # if self.task.done():
        #     self.task.result()
        if self.task2.done():
            self.task2.result()
        
    def compose(self) -> ComposeResult:
        # tree: Tree[dict] = Tree("",classes="logtree",id=self.switcher_tree_id)
        # tree.root.expand()
        aaaa = []
        
        with Vertical():
            with ContentSwitcher(initial=self.switcher_ids[0],classes="convo_switcher"):  
                yield Convo(*aaaa, classes="convo",id=self.switcher_conv_id)
            yield MessageInputBox(id="pp"+uuid.uuid4().hex)

    def on_mount(self) -> None:
        pass


    async def pipe_message_to_ai(self,msg):
        self.queueinbound.put_nowait(msg)
        ppc:PPC = self.app.ppc
        await ppc.usermsg(self.conv_id,msg)

    async def update_response_loop(self, aqueue:asyncio.Queue):
        
        current_msg_ids = {}
        langgraph_idx_to_tree = {}
        current_langgraph_idx = None
        while True:

            if not self.is_mounted:
                await asyncio.sleep(0.5)
                continue

            # Get a "work item" out of the queue.
            msg_info = await aqueue.get()
            
            if len(msg_info) == 1:
                # this is a log message
               
                log_msg = msg_info[0]

                
                log_op = log_msg["op"]  
                log_path = log_msg["path"] # / separated path ; can be empty string, it means the root.
                log_value = log_msg["value"] # the value of the log, its a dict with key values.

                # split the path into little pieces
                
                if log_path == "":
                    if log_op == "replace" and "id" in log_value:
                        # it is a new message 
                        current_langgraph_idx = log_value["id"]
                        if current_langgraph_idx not in langgraph_idx_to_tree:

                            # create a new tree
                            new_tree_id = "pp_"+uuid.uuid4().hex
                            new_tree = Tree("",classes="logtree",id=new_tree_id)
                            
                            langgraph_idx_to_tree[current_langgraph_idx] = new_tree
                            self.switcher_ids.append(new_tree_id)

                            new_tree = langgraph_idx_to_tree[current_langgraph_idx]
                            cs = self.query_one(ContentSwitcher)
                            await cs.mount(new_tree)
                            def after_refresh(idx):
                                #await asyncio.sleep(0.1)
                                cs = self.query_one(ContentSwitcher)
                                cs.current = idx
                                
                                for child in cs.children:
                                    child.display = bool(idx) and child.id == idx
                            
                            self.app.call_later(after_refresh,self.switcher_ids[0])
                                
                            

                    # make it add at the root that way
                    path_parts = [""]
                        
                else:
                    path_parts = log_path.split("/")
                    if path_parts[0] == "":
                        path_parts = path_parts[1:]


                if the_tree := langgraph_idx_to_tree.get(current_langgraph_idx,None):
                    # get the root of the tree
                    root = the_tree.root

                    # set the values to the tree 
                    set_tree_value(root, log_op, path_parts, log_value)

            else:

                convo_element:Convo = self.query_one("Convo")
                msg_id, sendername, msgchunk = msg_info
                strd = datetime.datetime.now().strftime("%H:%M")

                if msg_id not in  current_msg_ids :
                    # creating a message 
                    other_msg =OtherMsg("")
                    # append the message to the convo
                    await convo_element.append_msg(other_msg)

                    other_msg.msg_id = msg_id
                    other_msg.tree_id = langgraph_idx_to_tree[current_langgraph_idx].id

                    current_msg_ids[msg_id] = other_msg


                other_msg:OtherMsg = current_msg_ids[msg_id] 
                other_msg.username = sendername
                other_msg.msg_content += msgchunk
                other_msg.msg_time = strd
                convo_element.timer_scroll_end()
            
            # declare job done

        

    async def on_key(self, event: events.Key) -> None:
        pass
        #if event.key == "l":
        #    convo = self.query_one(Convo)
        #    msg = convo.get_the_message_at_curr_idx()
        #    if isinstance(msg,OtherMsg):
        #        tree_id = msg.tree_id
        #        cs = self.query_one(ContentSwitcher)
        #        if cs.current == tree_id:
        #        
        #            cs.current = self.switcher_conv_id
        #        else:
        #            cs.current = tree_id
                

    async def on_button_pressed(self) -> None:
        msg:TextArea = self.query_one(".messageinputarea")
        await self.pipe_message_to_ai( msg.document.text )
        msg.clear()
        msg.focus()

class OtherMsg(BorderTitledMsg):
    username = reactive("User")
    msg_time = reactive("")
    msg_content = reactive("")
    msg_id:str = reactive("")
    tree_id:str = reactive("")

    def on_mount(self) -> None:
        self.classes="othermsg"
    def watch_username(self, old_value, new_value):
        self.border_title = f"[i]{self.msg_time}[/i]  [b]{new_value}[/b]"

    def watch_msg_time(self, old_value, new_value):
        self.border_title = f"[i]{new_value}[/i]  [b]{self.username}[/b]"
    def watch_msg_content(self, old_value, new_value):
        ta = self.query_one(TextArea)
        ta.replace(new_value,ta.document.start,ta.document.end)
        #self.update(new_value)


class UserMsg(BorderTitledMsg):
    username = reactive("User")
    msg_time = reactive("")
    msg_content = reactive("")


    def on_mount(self) -> None:
        self.classes="usermsg"
    def watch_username(self, old_value, new_value):
        self.border_title = f"[i]{self.msg_time}[/i]  [b]{new_value}[/b]"

    def watch_msg_time(self, old_value, new_value):
        self.border_title = f"[i]{new_value}[/i]  [b]{self.username}[/b]"
    def watch_msg_content(self, old_value, new_value):
        ta = self.query_one(".message_text_area")
        ta.replace(new_value,ta.document.start,ta.document.end)
    

class ContactPanel(Static):

    convo_id_to_widget_id = {}

    class Selected(events.Message):
        def __init__(self, convo_id: str,widget_id:str) -> None:
            self.convo_id = convo_id
            self.widget_id = widget_id
            super().__init__()

    def compose(self) -> ComposeResult:
        yield ListView(
             *[],
                name="contact_list")

    def on_mount(self) -> None:
        self.styles.min_width = 8

    async def insert_in_contact_list(self,label,convo_id, widget_id):
        lv = self.query_one(ListView)
        await lv.mount( ListItem(Label(label), name=convo_id))

        self.convo_id_to_widget_id[convo_id] = widget_id

    def get_widget_id(self,convo_id) -> str:
        return self.convo_id_to_widget_id[convo_id]

    def on_list_view_selected(self,selected_msg:ListView.Selected):

        convo_id = selected_msg.item.name
        if convo_id in self.convo_id_to_widget_id:
            pass 
            # notify parent that the selected conversation has changed

            #cs = self.query_one(ContentSwitcher)
            #cs.current = self.convo_id_to_widget_id[selected_msg.item]
            self.post_message(self.Selected(convo_id,self.convo_id_to_widget_id[convo_id]))
        selected_msg.stop()


class ProfilePanel(Static):
    def compose(self) -> ComposeResult:
        
        yield Markdown("### Profile\n\nThis is your profile.")
        # Add the TabbedContent widget
        with TabbedContent(initial="jessica"):
            with TabPane("Leto", id="leto"):  
                yield Markdown("### Description: \n I can do book stuff")  
                with TabbedContent(initial="a"):
                    with TabPane("a", id="a"): 
                        yield Markdown("aaaa") 
                    with TabPane("b", id="b"): 
                        yield Markdown("bbbb") 
            with TabPane("Jessica", id="jessica"):
                yield Markdown("# hi \n ## this is content\n\n here. \n```python\nprint('hello')\n```")  # Tab content
        yield Footer()
    def on_mount(self) -> None:
        self.styles.min_width = 8

class UserPassPanel(Static):

    def compose(self):
        with Vertical():
            yield Label("Username:")
            yield Input(placeholder="username",max_length=20,classes="username")
            yield Input(placeholder="password",password=True,max_length=30,classes="password")
            yield Button("Login")
    def on_button_pressed(self) -> None:
        inpuser:Input = self.query_one(".username")
        inppass:Input = self.query_one(".password")
        btn:Button = self.query_one(Button)
        inpuser.disabled = True
        inppass.disabled = True
        btn.disabled = True
        async def on_b_p(u,p):
            ppc:PPC = self.app.ppc
            success = await ppc.login(u,p)

            if success:
                ppc.setup_token(success)
                await self.app.on_login_success(u)
            else:
                await asyncio.sleep(.1)
                #inpuser.clear()
                inpuser.disabled = False
                inppass.disabled = False
                btn.disabled = False
                inpuser.focus()
            
        self.app.call_later(on_b_p,inpuser.value,inppass.value)

class SimpleApp(App):
    CSS_PATH = "pp.tcss"
    ppc:PPC = None
    ws_task:asyncio.Task = None


    myuser_id = ""

    userscache = {}
    

    def compose(self) -> ComposeResult:

        #,ProfilePanel()
        # ContactPanel()
        yield Horizontal(UserPassPanel())#,DiscussionWidget())
    
    def on_mount(self):
        
        
        self.ppc = PPC(os.getenv("PPN_HOST","http://localhost:8000/"),
                       
                       os.getenv("PPN_WSHOST","ws://localhost:8000/")
                       )
    
    def on_contact_panel_selected(self, selected: ContactPanel.Selected) -> None:
        selected.convo_id
        selected.widget_id
        dws = self.query_one(DiscussionsWidgets)
        dswitch = dws.query_one(".discussion_switcher")
        dswitch.current = selected.widget_id
        #for child in cs.children:
        #    child.display = bool(dws.initial_discussion_id) and child.id == dws.initial_discussion_id
    
    async def wsreading_task(self,ppc:PPC):
        async def ta(ws:websockets.WebSocketClientProtocol):
            while True:
                wsmsg = await ws.recv()
                if isinstance(wsmsg,str):
                    
                    m = MessageWS.model_validate_json(wsmsg)

                    originator = m.originator
                    content = m.content
                    convo_id = m.convo_id
                    
                    #dws = self.query_one(DiscussionsWidgets)
                    cp = self.query_one(ContactPanel)
                    

                    dwid = cp.get_widget_id(convo_id)

                    dw:DiscussionWidget = self.query_one(f"#{dwid}")

                    strts = datetime.datetime.now().strftime("%H:%M")
                    if self.myuser_id == originator:
                        convo = dw.query_one(Convo)
                       
                        await convo.append_user_msg("-1",content,
                                                    self.get_nick_name(originator),
                                                    strts)

                    else:
                        anid = random_widget_id()
                        convo = dw.query_one(Convo)
                        await convo.append_other_msg(anid,content,
                                                    self.get_nick_name(originator),
                                                    strts)
                        #dw.aqueueoutput.put_nowait(({"op":"replace","path":"","value":{"id":anid}},))
                        #dw.aqueueoutput.put_nowait((anid, self.get_nick_name(originator), content))
                #qout:asyncio.Queue
                #qout.put_nowait(("id","dlfs","content"))
        await ppc.ws_client_connection(ta)

    def get_nick_name(self,user_id) -> str:
        return self.userscache[user_id]["nickname"]
    def my_nick_name(self)->str:
        return self.get_nick_name(self.myuser_id)
    
    async def on_login_success(self,usernameused):

        ppc = self.ppc
        if self.ws_task is None:
            self.ws_task = asyncio.create_task(self.wsreading_task(ppc))
            def check_asynctask_status():
                if self.ws_task.done():
                    try:
                        self.ws_task.result()
                    except Exception as e:
                        raise
            self.set_interval(0.1,check_asynctask_status)      
        

        # resync users
        all_users = await ppc.users()
        self.myuser_id = None
        self.userscache = {}
        for u in all_users:
            if u["name"] == usernameused:
                self.myuser_id = u["id"]
            self.userscache[u["id"]] = u

        # clean up ui
        await self.query_one(Horizontal).remove_children(UserPassPanel)

        # get the conversations from server 
        #convodata = [{"id": "1", "name": "live_chat"}, {"id": "2", "name": "second_chat"}, {"id": "3", "name": "yet_another_chat"}]
        # mount the contact Panel
        cp = ContactPanel()
        await self.query_one(Horizontal).mount(cp)

        # mount the list of discussions (it is the switcher of discussions)
        dws = DiscussionsWidgets()
        await self.query_one(Horizontal).mount(dws)
        cs = dws.query_one(ContentSwitcher)
        
        # fetch conversations
        convodata = await ppc.conv()

        convoidtodw = {}
        for convo in convodata:
            # for each conversation, create field in the contact Panel
            #await cplv.mount(ListItem(Label(f"@ {convo['name']}")))
            discussion_widget_id = random_widget_id()
            await cp.insert_in_contact_list(f"@ {convo['label']}",convo["id"],discussion_widget_id)

            # for each conversation, create a discussion widget
            dw = DiscussionWidget(id=discussion_widget_id)
            await cs.mount(dw)

            dw.user_nick_name = self.my_nick_name()
            dw.conv_id=convo["id"]
            convoidtodw[convo["id"]] = dw




        # reset the initial discussion id display
        for child in cs.children:
            child.display = bool(dws.initial_discussion_id) and child.id == dws.initial_discussion_id
        
        for convo in convodata:
            dw:DiscussionWidget = convoidtodw[convo["id"]]
            convo_content = await ppc.convid(convo["id"])
            convowidget = dw.query_one(Convo)
            for c in sorted(convo_content,key=lambda x:x["ts"]):
                c["id"],c["content"],c["ts"],c["sender"]
                strts = datetime.datetime.fromtimestamp(c["ts"]).strftime("%H:%M")
                if self.myuser_id == c["sender"]:
                    await convowidget.append_user_msg(c["id"],c["content"],
                                                self.get_nick_name(c["sender"]),
                                                strts,
                                                auto_scroll=False)
                                                
                else:
                    await convowidget.append_other_msg(c["id"],c["content"],
                                                    self.get_nick_name(c["sender"]),
                                                    strts,
                                                    auto_scroll=False)
            
            convowidget.timer_scroll_end()
            # [{'id': 1, 'content': 'fdsq', 'sender': 1, 'ts': 1714224104.39881}

if __name__ == "__main__":
    app = SimpleApp()
    #qi = app.query_one(DiscussionWidget).queueinbound
    #qo = app.query_one(DiscussionWidget).aqueueoutput
    #task = asyncio.create_task(manage_agent(qi, None, qo))
    app.run()