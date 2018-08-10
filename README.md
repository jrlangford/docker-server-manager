# Docker management script

A script that creates reproducible docker image builds and automates the
deployment of docker images that serve content through nginx.

## Goals
- Build docker images consistently
    - Only include files relevant to each build
    - Name images with tags related to their contents
- Automate the deployment of containers that serve resources through Nginx
- Provide practical commands to interact with container during development

## Features
- Build an image with its name based on the project's name, version, and
  current git commit hash
- Mount container volumes that hold static content to be served on the host
  (static content must be provisioned during container startup)
- Generate and deploy an nginx configuration file
- Autogenerate .dockerignore file based on the list of files not tracked by git
- Manage container with commands such as deploy, dismiss, and inspect

## Requirements
- git
- nginx
- python 3.6

## Basic Usage
**Install management script**

Run the following command from the working directory of the git repository you
want to manage
```bash
curl -O https://raw.githubusercontent.com/jrlangford/docker-server-manager/master/install.sh && \
    chmod +x install.sh && \
    ./install.sh
```

**Set up environment**

1. Create a file with your project's environment vars and name it *"{env}.env"*
2. Configure your serverconf json file and set the **env** name to *{env}*, the
   default serverconf file should be named *"serverconf.json"*
3. Store your project's version in  a file named *"version.txt"* in your
   working directory root

**Build image and deploy container**

Run `./server.py deploy`

**Dismiss container**

Run `./server.py dismiss`

## Detailed usage
The script is run by executing `./server.py [options] command`.

Note: It generates temporary files in your working directory in directories
named with the following prefix: *".dcm\_env\_"*

### Options
#### -f FILE
Use `FILE` as the serverconf file to be used. Cannot be used in conjunction
with *-e*
#### -e ENVIRONMENT
Use *"serverconf.{ENVIRONMENT}.json"* as the serverconf file to be used. Cannot
be used in conjunction with *-f*
#### -c CMD
Run container overriding default initial command with *CMD*.
### -i
Run the container with the *-it* docker flags.
#### -h
Show help

### Commands
#### build
Rewrite the .dockerignore file and build image.
#### run
Run image, also build it if one corresponding to the current git hash and index
state does not exist.
#### start
Start a stopped container
#### stop
Stop a running container
#### clean
Stop and remove container, clean temporary files created by script.
#### logs
Show container's logs
#### bash
Exexcute bash in a running container
#### ndeploy
Generate nginx configuration file and deploy it by copying it to the specified
nginx directory, testing the new configuration and reloding it.
#### nclean
Remove container's nginx configuration from the specified nginx directory, test
the new configuration, and reload it. Remove nginx conf file from temporary
files directory.
#### deploy
Execute **run** followed by **ndeploy**
#### dismiss
Execute **nclean** followed by  **clean**.
#### reload
Stop container, remove it, and relaunch it with the port mappings it originally
had.
#### hup
Send sighup to running container's PID 1.

## The serverconf file
This is a json file that stores your build and deployment configuration. An
example `serverconf.example.json` file is included in this repository.

### env
Name of the current working environment, the container will run with the
environment files defined in a file named *"{env}.env"*.
### repository\_name
Base name that will be used for naming images and containers.
### existing\_tag
Tag of an existing internal or external(e.g. from docker hub) image with base
**repository_name**. If defined, the script will not build an image and instead
attempt to run non-build-related commands on the image with the name
*{repository\_name}:{existing\_tag}*.
### default\_mountbase
Directory in which the script can automatically create mountpoints for container
volumes. Volumes which have their **host** set to *"default"* will use this as a
base directory.Ensure your user has read and write permissions on it.
### nginx\_dyn\_conf\_dir
Directory in which the script will place automatically generated nginx
configuration files. Ensure your user has read and write permissions on it and
that the base nginx configuration file loads the configuration files in this
directory.
### build\_dirty
If set to *true* the script will not generate a .dockerignore file.
### volumes
An array of volume objects that will be mounted on the container.

#### tag
A name used by the script to refer to the volume.
#### cont
The path in the container where the volume will be mounted.
#### host
The host directory that will be mounted on the container.

If not specified, the volume will be managed by docker using **tag** for its
name and mounted on the **cont** directory of the container.

If set to *"default"* a directory in **default\_mountbase** will be created and
bind mounted on the **cont** directory of the container.

If set to *"pwd"* the current directory will be bind mounted on the **cont**
directory of the container. This is practical for development environments.

If set to a valid system path, the directory in the defined path  will be bind
mounted on the **cont** directory of the container.
### auto\_clean
If set to *true* the contents of the volume are deleted when the `clean`
command is run.

### server\_map
An array of container service objects that will be served through nginx.

#### c\_port
The container exposed port listening for requests expressed in its full form:
*{port}/{protocol}*.

Make sure your Dockerfile exposes this port through the
**EXPOSE** command.
#### v\_host
The domain name that will be used to access the service.

e.g. *"api.mywebsite.com"*

#### volumes\_served
An array of volume served objects that serve content through the defined
**v\_host**.

##### tag
The tag of any bind mounted volume defined in **volumes**.
##### location
The nginx location where the contents will be served.

### networks
An array of strings containing the docker networks the container should connect
to.


## Troubleshooting

### Cannot build docker image, files from the repo are not being copied into container
**Cause:**
When the image is built .dockerignore is recreated with the contents of all
files not being tracked by git. Your Dockerfile may be referencing files that
are not being included in the build's context.

**Solution:**
Add the *"build_dirty"* name set to *true* to your serverconf file, then remove
*".dockerignore"*; the file won't be recreated during the following builds,
during which every file in your working directory will be added to docker's
build context.
