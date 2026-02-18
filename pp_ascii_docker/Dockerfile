# this is the docker file for the pp_ascii TUI application. 
# The application is a terminal based UI.
# This docker is a simple example of how to serve the application through ssh.
FROM python:3.12

# install ubuntu packages
RUN apt-get update && apt-get install -y \
    # open ssh server 
    openssh-server \
    && rm -rf /var/lib/apt/lists/*

# create a simple user with no password
RUN useradd -m -s /app/pp_ascii/textualpp.py user
RUN passwd -d user

# Install the required packages
ADD pp_ascii_docker/pp_txtui_reqs.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

# Copy the source code
ADD pp_ascii /app/pp_ascii

# we need the schemas from the backend and the api client.
RUN mkdir /app/ppback/
ADD ppback/ppschema.py /app/ppback/
RUN touch /app/ppback/__init__.py
ADD ppback/apiclient.py /app/ppback/

# change execution for the main file
RUN chmod +x /app/pp_ascii/textualpp.py

# prepare the ssh server configuration
ADD pp_ascii_docker/sshd_config /etc/ssh/sshd_config
RUN mkdir -p /var/run/sshd

# windows user gonna inject environement in the windows format :(
# add pp_ascii_docker/environment /etc/environment
RUN echo "PYTHONPATH=\"/app\"" > /etc/environment
# add the app directory to the PYTHONPATH
ENV PYTHONPATH /app


# take the var env and put it the /etc/environment. So that you can configurate the file from var env
ENTRYPOINT echo "PPN_HOST=$PPN_HOST\nPPN_WSHOST=$PPN_WSHOST" >> /etc/environment && /usr/sbin/sshd -D
# CMD is ssh server 
# CMD ["/usr/sbin/sshd", "-D"]

EXPOSE 2222