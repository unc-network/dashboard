# OCNES Docker Development Environment

**OCNES** is a dashboard program with the following requirements:
- **Python** 3.8+
- various `pip` modules, including `python-auth-ldap`, which in turn requires that the Linux system this runs on has certain packages installed
- **Django** web framework, which itself has certain requirements:
	- Has an ORM (Object Relational Mapper) that requires a database such as **SQLite** or **PostgreSQL** to store its information
	- When first deployed and after any model changes, Django must migrate its data models to the underlying database
- **Celery**, "an open source asynchronous task queue or job queue which is based on distributed message passing," which runs independently of Django
- **Redis**, "an in-memory data structure store, used as a distributed, in-memory key–value database, cache and message broker, with optional durability", which also runs independently
- **Gunicorn**, 'the "Green Unicorn" is a Python Web Server Gateway Interface HTTP server', used to run Django in production

Along with this, there are some caveats regarding which RDBMS to use:
- **SQLite** stores everything in a single file.  It is far easier to setup and use than PostgreSQL.  Unfortunately, being a single file, this leads to potential contention if multiple processes need access to the database, as is the case here.  Celery and Django run independently.  As both attempt to access the ORM, this results in file locking that causes contention.  So SQLite is not ideal here.
- **PostgreSQL** is fare more robust and scalable, as it is a proper multi-user RDBMS engine that can be hosted locally and accessed via sockets or hosted remotely and reached via a network connection.  However, PostgreSQL requires additional work up front to create users, set permissions, and define databases.

As can be seen, setting up a development environment to match the production setup can be time consuming.  Add in the differences between Windows, macOS, and Linux development environments, it can present a challenge.

But with Docker, there is an alternative.  With just Docker Desktop installed on Windows or macOS, or Docker engine installed on a preferred Linux distro, all that is required are the Docker configuration files contained here.


# Setup
### 1. Download/install the appropriate container tech--e.g., Docker or some containerd based offering--such as [Docker Desktop](https://docs.docker.com/desktop/release-notes/) or [Rancher Desktop](https://rancherdesktop.io/) for your particular OS.

**NOTE**:  If you use **Rancher Desktop**, either
- select the `dockerd (moby)` container engine to use, or
- if you prefer to run everything using the OCI standard `containerd` so that you can have both your cake (Kubernetes) and eat it, too, (Docker), then make sure to add an `alias docker=nerdctl` to the appropriate shell config.  The instructions and files here assume that the CLI tool is called `docker`.

### 2. Start Docker/Rancher Desktop
### 3. Bring up a Terminal/shell and navigate to the directory containing this file and the other Docker config files including `docker-compose.yml`
### 4. Create a file called `.env` to store your local environment variables.  This file should be saved in the same directory as `docker-compose.yml`.  It defines your local environment and should look something like the following (adjust as needed):

```bash
# Copy the example file
cp env.example .env
```

At the minimum, you should set the DJANGO_SECRET to something unique and the AKiPS server, username, and password.

With this file in place, and noting that `.gitignore` does not upload this, you can have your instance running quickly and easily.

### 5. Run the following command to bring up the entire environment in one step (where you can see logs):

```bash
# To see logs similar to running `python manage.py runserver`
docker compose up
# To run in the background
docker compose up -d
```

#### NOTES:
- This will build and spin up a series of containers running the following services:
	- **Redis**
	- **PostgreSQL**
	- **Celery**
	- the main **OCNES Django project** hosted via Gunicorn
- On startup of the OCNES container, it will first run `migrate` to ensure the database is up to date
- `-d` means to daemonize the containers, so it runs the containers in the background and returns you to your shell prompt.  
	If you *do not use* this flag, `docker compose` stays running in your terminal/shell session, and hitting `[CTRL][C]` will shut all the containers back down.  You might want to do this so that you can see all the log output from the 4 containers, because when you daemonize them you will not see that output.  Simply use a second terminal session for any other CLI work.
- Think of this as running 4 distinct servers, each self-contained yet able to cross-communicate, within the host machine.
	- Celery can access Redis and PostgreSQL.
	- OCNES/Django can access PostgreSQL.
	- Both OCNES and Celery map the project source files into their respective containers, meaning they access the same files as the host running these containers.  So any changes made locally on the host will be reflected in those containers automatically.
- The first time this command is executed, it may take a few minutes, as it has to download images from an image registry such as `hub.docker.com` and build a few of the container images.  Once built, however, this command should come up within seconds on successive executions.
- To confirm your containers are running, you can execute the following command from a terminal/shell:

```bash
docker ps
```

You should see output similar to the following:

```bash
% docker ps
CONTAINER ID   IMAGE              COMMAND                  CREATED          STATUS          PORTS                    NAMES
2db59cb0b51b   dashboard-ocnes    "gunicorn wsgi"          24 minutes ago   Up 24 minutes   0.0.0.0:8000->8000/tcp   dashboard-ocnes-1
25a15defd164   dashboard-celery   "celery --app projec…"   24 minutes ago   Up 24 minutes   0.0.0.0:5672->5672/tcp   dashboard-celery-1
e260082c2293   postgres:latest    "docker-entrypoint.s…"   24 minutes ago   Up 24 minutes   0.0.0.0:5432->5432/tcp   dashboard-db-1
c03c18689ee3   redis:7-alpine     "docker-entrypoint.s…"   24 minutes ago   Up 24 minutes   0.0.0.0:6379->6379/tcp   dashboard-redis-1
```

- The OCNES/Django and Celery images, which are built locally for this project, will be named for the directory that `docker-compose.yml` was in when created.  (If you are an OOP programmer, think of images as classes and containers as instances of those classes.)  So you should see `dashboard-ocnes` and `dashboard-celery` as images.  And the active containers will be named `dashboard-ocnes-1` and `dashboard-celery-1`.  (Docker numbers each instance it spins up.)  This is handy to know since you can access running containers using `docker exec`.
- Note that if you are using **Rancher Desktop** that the container names use underscores ("_") instead of dashes("-"), meaning the above would appear as `dashboard_ocnes_1` and `dashboard_celery_1`.

### 6. After the initial launch (and every subsequent time you spin up this container), the PostgreSQL container instance is already preconfigured/updated through `migrate`.  However, should you need to do any manual work with the Django admin tools, simply execute the following command, which will place you *inside* the OCNES container:

```bash
docker exec -it dashboard-ocnes-1 /bin/bash
```

- When you are inside a container, you should be at a `#` prompt (since you are root), and if in the OCNES or Celery containers, it should place you right in the `/dashboard` directory where the OCNES project files are located.  At this point you can do the usual commands such as `python manage.py migrate`, etc.

### 7. At this point, all the pieces are running and you have all migrations done.  However, you are not done yet.  You do not yet have a super user defined that you can log into OCNES with.  So next enter the following command in the OCNES container:

```bash
python manage.py createsuperuser
```

- Type in a username and hit `Enter`
- Type in or leave blank the email address and hit `Enter`
- Type in a password and hit `Enter`
- Repeat the password and hit `Enter`

### 8. At this point, you have the basics done.  Exit the running container by entering `exit`
### 9. Point your web browser at http://127.0.0.1:8000 and see the login page.
### 10. Enter the username and password you provided earlier, and voila!  Welcome to OCNES!
### 11. When you are finished, you can spin down the containers by pressing `[CTRL][C]` or, if you used `-d` when bringing up the containers, you can use

```bash
docker compose down
```


# Initial Configuration

# Development Workflow

Once setup, the workflow goes as follows.  Assuming that Docker is up and running,

### 1. In your terminal/shell, navigate to the project root directory where these Docker files, notably `docker-compose.yml`, are located.

### 2. Enter

```bash
docker compose up
```

You now have a running OCNES instance where you can see color-coded log entries based on which container's logs are being shown.  This can be very handy during development.

### 3. Do your development work, editing Django files/etc. as usual in your preferred editor/IDE.
  - If you modify models which then require performing a Django `makemigrations` followed by a `migrate`, either bring down the PostgreSQL containter using a command like `docker compose down db` followed by `docker compose up db`, or simply enter the running **OCNES container** as follows:

```bash
# Check what containers are running
docker ps
# Remote into the OCNES container
docker exec -it dashboard-ocnes-1 /bin/bash
```

and perform the necessary steps inside the container:

```bash
python manage.py makemigrations
python manage.py migrate
exit
```

### 4. When you are finished working, you can simply spin down the containers by pressing `[CTRL][C]` or using

```bash
docker compose down
```

if you used the `-d` flag with `docker compose up`.


## NOTES
- If you are running on an ARM64-based system such as an **Apple Silicon/M1 Mac**, you should be able to build the containers as ARM64 native binaries for maximum performance/efficiency by adding the environment variable `DOCKER_ARCH="arm64v8/"`, such as using

```bash
DOCKER_ARCH="arm64v8/" docker compose up
```

or, better yet, adding that environment variable to your `.env` file.

- The setup as defined has the PostgreSQL container storing all data within a Docker volume named `db-data`.  This is to provide persistence across container restarts.  Note that if you ever want to "reset" PostgreSQL back to its initial state, simply delete this Docker volume as follows:

```bash
# List Docker volumes
docker volume ls
# Determine the PostgreSQL volume by finding the one with `db-data` in the name; e.g., `dashboard_db-data`
# Remove this volume
docker volume rm dashboard_db-data
```

- In an earlier version of the `docker-compose.yml` file, the PostgreSQL data was stored in a hidden directory within the code base.  Because of this persistent storage, `.gitignore` has an entry to ignore `.docker/` altogether.  If you still have this, feel free to delete it.
- Any time there are updates to **Redis**, **Celery**, **PostgreSQL**, etc., that you wish to take advantage of, or you simply want to make sure that you are using the latest build of a container, you can simply add `--build` to force a rebuild of the images:

```bash
docker compose up --build
```

- If you ever wish to "burn the Docker setup to the ground", you can either
	- Go into **Docker Desktop | Preferences...**, click the troubleshooting (bug) icon at the top right, and click on `Clean / Purge data`, or
	- Run the script `docker-remove.sh` which will perform all the following steps (or perform them manually):
		- Shut down all running OCNES Docker containers using `docker compose down`
		- Remove all Docker containers, images, and volumes, along with the PostreSQL data store, using the following commands:
```bash
# Remove containers (instances of images)
docker container rm -f $(docker container ls -aq)
# Remove images
docker image rm -f $(docker image ls -q)
# Remove volumes (data created/stored within containers;
# this includes the PostgreSQL db-data Docker volume)
docker volume rm -f $(docker volume ls -q)
# OLD step below
# rm -rf .docker/
```
