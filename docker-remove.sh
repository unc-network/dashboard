#!/bin/zsh
echo '**********************************************************************'
echo 'This script removes EVERYTHING related to the OCNES Docker setup,'
echo 'including the PostgreSQL data store.  Be sure you want to do this.'
echo ''
echo 'Press [CTRL][C] NOW to abort'
echo '**********************************************************************'
echo
read -s -k '?          [Press any key to continue]'
echo ''
# Remove everything Docker
echo 'Shutting down Docker containers...'
docker compose down
echo 'Remove containers (instances of images)...'
docker container rm -f $(docker container ls -aq)
echo 'Remove images...'
docker image rm -f $(docker image ls -q)
echo 'Remove volumes (data created/stored within containers)...'
docker volume rm -f $(docker volume ls -q)

# Remove PostgreSQL data
echo 'Remove hidden Docker PostgreSQL data directory...'
rm -rf .docker/

echo 'System clean.'
