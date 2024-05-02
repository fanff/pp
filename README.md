
## PP Network


The PP Network is a straightforward backend conversational infrastructure designed to support real-time messaging capabilities. 

It features 
* user authentication with login and password, 
* multiple conversation threads
* The API is intentionally simple, facilitating easy interactions for sending and receiving messages. 
* WebSockets for real-time communication, enabling continuous, bidirectional exchanges between clients and the server.
* A simple TUI client for testing the backend.


#### Development mode: 

You might want to make sure the root of your project is considered inside PYTHONPATH. 

In laucnch.json of vscode:
```json
"env": {
    "PYTHONPATH": "${workspaceFolder}"
}
```

Or, at the powershell command line 

`$env:PYTHONPATH += ";$PWD" `

Or, if prefered a volume mount in the compose.yml can make the job as well. 

#### testing images with docker : 

Use the compose.yml file at will. 

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


### Docker images building :

Backend API:
`docker build -f Dockerfileback -t pp_back .`

TUI accessible throu ssh.
`docker build -f Dockerfile -t pp_ascii_cli .`


Front end as a godot packaged application:
`docker build -f Dockerfile_god -t pp_frnt .`





### todo list 

[X] make datetime working 
[X] make message grouping together 
[X] fix the line edit to be multi line
[ ] make bot joining conversation 
[ ] fix the buttons do something about it 
[ ] fix the Send button
[ ] Set a fixed color for each user 
[ ] sort out why dynamodb not working https://docs.sqlalchemy.org/en/13/dialects/

[ ] make admin api for managing users ? 
[X] update the logo splash screen 
[ ] make some more sprite sheets for 16x16 
