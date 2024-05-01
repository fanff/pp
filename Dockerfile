
FROM python:3.12

# install ubuntu packages
RUN apt-get update && apt-get install -y \
    # open ssh server 
    openssh-server \
    && rm -rf /var/lib/apt/lists/*


ADD sshd_config /etc/ssh/sshd_config
RUN mkdir /var/run/sshd


# Create a non-root user anonymous without password
RUN useradd -m -s /bin/bash anonymous
# create a sumple user with simpel password 
RUN useradd -m -s /app/pp_ascii/textualpp.py user
RUN echo 'user:password' | chpasswd



# Install the required packages
ADD pp_txtui_reqs.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

# Copy the source code
ADD pp_ascii /app/pp_ascii

# we need the schemas from the backend
RUN mkdir /app/ppback/
ADD ppback/ppschema.py /app/ppback/
ADD ppback/__init__.py /app/ppback/
ADD ppback/thedummyclient.py /app/ppback/

# change execution for the main file
RUN chmod +x /app/pp_ascii/textualpp.py

# add the app directory to the PYTHONPATH
ENV PYTHONPATH /app

# entrypoint is ssh server 
CMD ["/usr/sbin/sshd", "-D"]

EXPOSE 2222