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
- **SQLite** stores everything in a single file.  It is far easier to setup and use than PostgreSQL.  Unfortunately, being a single file, this leads to potential contention if multiple processes need access to the database, as is the case here.
- **PostgreSQL** is fare more robust and scalable, as it is a proper multi-user RDBMS engine that can be hosted locally and accessed via sockets or hosted remotely and reached via a network connection.  However, PostgreSQL requires additional work up front to create users, set permissions, and define databases.

As can be seen, setting up a development environment to match the production setup can be time consuming.  Add in the differences between Windows, macOS, and Linux development environments, it can present a challenge.

But with Docker, there is an alternative.  With just Docker Desktop installed on Windows or macOS, or Docker engine installed on a preferred Linux distro, all that is required are the Docker files contained here.

## Setup
1. Download/install the appropriate [Docker software](https://docs.docker.com/desktop/release-notes/) for your particular OS
2. Start Docker
3. Bring up a Terminal/shell and navigate to the directory containing this file and the other Docker files including `docker-compose.yml`
4. Run the following command to bring up the entire environment in one step:
```
docker compose up
```
- This will build and spin up a series of containers running the following services:
	- Redis
	- PostgreSQL
	- Celery
	- the main OCNES Django project hosted via Gunicorn
- The first time this is done, it may take a minute, as it has to download images and build a few of the container images.  Once built, however, this command should come up within seconds.

5. After the initial launch, the PostgreSQL container instance is empty and it is necessary to run the Django `makemigrations` command.  This only needs to be done once to get started.  To do this, execute the following command, which will place you inside the OCNES container:
```
docker exec -it dashboard-ocnes-1 /bin/bash
```
6. You should now be a `#` prompt within that container, and it should place you right in the `/dashboard` directory where the OCNES project files are located.  So now execute the following command:
```
python manage.py migrate
```
7. Once complete, we have setup the database tables.  However, we are not done yet.  WE do not yet have a user defined that we can log into OCNES with.  So next enter the following command:
```
python manage.py createsuperuser
```
- Type in a username and hit `Enter`
- Type in or leave blank the email address and hit `Enter`
- Type in a password and hit `Enter`
- Repeat the password and hit `Enter`
8. At this point, you have the basics done.  Exit the running container by entering `exit`
9. Point your web browser at http://127.0.0.1:8000 and see the login page.
10. Enter the username and password you provided earlier, and voila!  Welcome to OCNES!
11. When you are finished, you can spin down the containers using
```
docker compose down
```

## Development Workflow

Once setup, the workflow goes as follows.  Assuming that Docker is up and running,
1. In your terminal/shell, navigate to the project root directory where these Docker files are located.

2. Enter
```
docker compose up
```

3. Do your development work, editing Django files/etc. as usual in your preferred editor/IDE.
	- If you modify models which then require performing a Django `makemigrations` followed by a `migrate`, enter the running OCNES container and perform the necessary steps there as follows:
```
docker exec -it dashboard-ocnes-1 /bin/bash
```
then, inside the container
```
python manage.py makemigrations
python manage.py migrate
exit
```

4. When you are finished working, you can simply spin down the containers using
```
docker compose down
```

## NOTES
- The setup as defined has the PostgreSQL container storing all data within a hidden directory at the root of the project files; specifically, in `.docker/pgdata/`.  This is to provide persistence.  Note that if you ever want to "reset" PostgreSQL back to its initial state, simply delete this directory.
- Because of this persistent storage, `.gitignore` has an entry to ignore `.docker/` altogether.
- Any time there are updates to Redis, Celery, PostgreSQL, etc., that you wish to take advantage of, you can simply add `--build` to the end of `docker compose up`  and it will force a rebuild of the images.
- If you ever wish to "burn the Docker setup to the ground", you can either
	- Go into **Docker Desktop | Preferences...**, click the troubleshooting (bug) icon at the top right, and click on `Clean / Purge data`, or
	- you can enter the following commands in your terminal/shell:
```
# Remove containers (instances of images)
docker container rm -f $(docker container ls -aq)
# Remove images
docker image rm -f $(docker image ls -q)
# Remove volumes (data created/stored within containers)
docker volume rm -f $(docker volume ls -q)
```
