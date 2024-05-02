
## PP Network


The PP Network is a straightforward backend conversational infrastructure designed to support real-time messaging capabilities. 

It features:

* user authentication with login and password, 
* multiple conversation threads
* The API is intentionally simple, facilitating easy interactions for sending and receiving messages. 
* **WebSockets** for real-time communication, enabling continuous, bidirectional exchanges between clients and the server.
* A simple TUI client for testing the backend; made with [Textual](https://textual.textualize.io/)
* A UI client made with [godot engine](https://godotengine.org/)

## Development mode: 

Just install the requirements.txt in your virtual environment and run the backend with the following command: 

```bash

uvicorn ppback.main:app --reload

```

Database initialization is done with the following command: 

```bash
python ppback/init_db.py
```
Default user passowrd are "fanf:fanf" and "ted:ted". (Me and my teddy bear )

The TUI client can be run with the following command: 

```bash
export PPN_HOST="http://backend:8000/"
export PPN_WSHOST="ws://backend:8000/"
python pp_ascii/textualpp.py
```


You might want to make sure the root of your project is considered inside PYTHONPATH. 

In laucnch.json of vscode:
```json
"env": {
    "PYTHONPATH": "${workspaceFolder}"
}
```

Or, at the powershell command line 

`$env:PYTHONPATH += ";$PWD" `

Or, if prefered a volume mount in the compose.yml can make the job as well if you prefer not having the venv in your project but inside the docker.


## Testing the docker composed application

Use the compose.yml file at will to start the whole application.

```bash 

# build the whole image set
docker compose build

# start up
docker compose up -d 

# to init the database there is a init_db.py script that can be run once.
docker compose exec backend python /app/ppback/init_db.py

# grab logs 
docker compose logs -f 
```

Since the TUI client is not yet dockerized, you can run it locally with the following command: 

```bash
ssh -p 2222 user@localhost
```

### Docker images building :



Backend API:
`docker build -f Dockerfileback -t pp_back .`

TUI accessible throu ssh.
`docker build -f Dockerfile -t pp_ascii_cli .`


### todo list 

Backend TODO list : 


* [ ] make bot joining conversation 
* [ ] Set a fixed color for each user 
* [ ] sort out why dynamodb not working at initdb https://docs.sqlalchemy.org/en/13/* dialects/
* [ ] move to poetry dependency mngment

Frontend TODO list :

* [X] make datetime working 
* [X] make message grouping together 
* [X] fix the line edit to be multi line
* [ ] make admin api for managing users ? 
* [X] update the logo splash screen 
* [ ] make some more sprite sheets for 16x16 
