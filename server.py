#!/usr/bin/env python3.6
import subprocess
import sys
import os
import secrets
import json
from pathlib import Path
from shutil import copyfile, rmtree
from jinja2 import Template

ENV=None
REPOSITORY_NAME=None
CONTAINER_STATIC_DIR=None
HOST_STATIC_DIR=None
NGINX_DYN_CONF_DIR=None
VIRTUAL_HOST=None
HOST_PORT=None
CONTAINER_PORT=None

ENVDIR = 'environment'
CIDFILE=ENVDIR+"/cidfile"
SECRET_KEY_FILE=ENVDIR+"/s_key"
STATIC_DIR_FILE=ENVDIR+"/static_dir"
NGINX_TEMPLATE='nginx.conf.jn2'
NGINX_CONF_LOCATION_FILE=ENVDIR+"/nginx_conf_location"

def load_conf():
    global ENV
    global REPOSITORY_NAME
    global CONTAINER_STATIC_DIR
    global HOST_STATIC_DIR
    global NGINX_DYN_CONF_DIR
    global VIRTUAL_HOST
    global HOST_PORT
    global CONTAINER_PORT

    c = None
    with open('serverconf.json','r') as f:
        c =  f.read().rstrip()
    jconf = json.loads(c)

    ENV=jconf['env']
    REPOSITORY_NAME=jconf['repository_name']
    CONTAINER_STATIC_DIR=jconf['container_static_dir']
    HOST_STATIC_DIR=jconf['host_static_dir']
    NGINX_DYN_CONF_DIR=jconf['nginx_dyn_conf_dir']
    VIRTUAL_HOST=jconf['virtual_host']
    HOST_PORT=jconf['host_port']
    CONTAINER_PORT=jconf['container_port']

def pipe(command):
    o = subprocess.run(command, shell=True, stdout=subprocess.PIPE)
    if(o.returncode != 0):
        sys.exit(o)
    return o.stdout.rstrip().decode("utf-8")

def nopipe(command):
    o = subprocess.run(command,shell=True)
    if(o.returncode != 0):
        sys.exit(o)

def get_version():
    with open('version.txt','r') as f:
        return f.read().rstrip()

def get_image_name():
    githash = pipe("git rev-parse --short HEAD")
    tag = get_version()+'-'+githash
    return REPOSITORY_NAME+':'+tag

def get_cid():
    with open(CIDFILE,'r') as f:
        return f.read()

def get_static_dir():
    with open(STATIC_DIR_FILE,'r') as f:
        return f.read()

def get_container_name():
    return pipe("docker inspect --format='{{.Name}}' "+get_cid()).lstrip("/")

def generate_nginx_conf():
    text = None
    with open(NGINX_TEMPLATE,'r') as f:
        text = f.read()

    portsString = pipe("docker inspect --format='{{json .NetworkSettings.Ports}}' "+get_cid())
    ports = json.loads(portsString)

    t = Template(text)
    o = t.render(
        port=ports['8000/tcp'][0]['HostPort'],
        virtual_host=VIRTUAL_HOST,
        static_dir=get_static_dir()
    )

    container_name = get_container_name()

    file_name = ENVDIR+'/'+container_name+'.conf'

    with open(file_name, "w") as text_file:
        text_file.write(o)

def copy_nginx_conf():
    container_name = get_container_name()
    file_name = container_name+'.conf'
    source = ENVDIR+'/'+file_name
    target = NGINX_DYN_CONF_DIR+'/'+file_name

    copyfile(source, target)

    with open(NGINX_CONF_LOCATION_FILE, "w") as text_file:
        text_file.write(target)

def test_nginx_conf():
    nopipe("nginx -t")

def read_nginx_conf_location():
    with open(NGINX_CONF_LOCATION_FILE,'r') as f:
        return f.read().rstrip()

def reload_nginx_conf():
    nopipe("nginx -s reload")

def clean_nginx():
    os.remove(read_nginx_conf_location())
    test_nginx_conf()
    reload_nginx_conf()
    os.remove(NGINX_CONF_LOCATION_FILE)

# Note: Deployment of only one environment at a time is supported
def ndeploy():
    generate_nginx_conf()
    copy_nginx_conf()
    test_nginx_conf()
    reload_nginx_conf()

def build_image():
    command = "docker build -t {} .".format(get_image_name())
    nopipe(command)

def run(env):
    if(env is None):
        sys.exit("Failed, missing environment parameter")

    envfile="."+env+".env"

    e = Path(envfile)
    if not e.is_file():
        sys.exit(envfile+" not found")

    c = Path(CIDFILE)
    if c.is_file():
        sys.exit("Failed, CIDFILE present: "+CIDFILE)

    image_name = get_image_name()

    command = "docker images -q "+image_name
    matching_images = pipe(command)
    if(matching_images==''):
        build_image()

    secret_key=secrets.token_urlsafe()

    with open(SECRET_KEY_FILE, "w") as text_file:
        text_file.write(secret_key)

    container_name = env+'-'+REPOSITORY_NAME

    static_dir = HOST_STATIC_DIR+container_name

    with open(STATIC_DIR_FILE, "w") as text_file:
        text_file.write(static_dir)

    if not os.path.exists(static_dir):
        os.makedirs(static_dir)

    command = " \
        docker run -d \
            --name={} \
            --env-file={} \
            --env='S_KEY={}' \
            --publish={}:{} \
            --volume={}:{} \
            --cidfile={} \
            {}".format(
            container_name,
            envfile,
            secret_key,
            HOST_PORT,
            CONTAINER_PORT,
            static_dir,
            CONTAINER_STATIC_DIR,
            CIDFILE,
            image_name
        )

    nopipe(command)

def start_container():
    nopipe("docker start "+get_cid())

def stop_container():
    nopipe("docker stop "+get_cid())

def remove_container():
    nopipe("docker rm "+get_cid())

def clean_static_dir():
    start_container()
    command = "docker exec {} bash -c 'rm -rf {}/*'".format(
        get_cid(),
        CONTAINER_STATIC_DIR
    )
    nopipe(command)

def clean():
    p = Path(NGINX_CONF_LOCATION_FILE)
    if p.is_file():
        sys.exit("Failed, clean nginx installation with 'nclean' before proceeding.")
    clean_static_dir()
    stop_container()
    remove_container()
    rmtree(get_static_dir())
    rmtree(ENVDIR)

def logs():
    nopipe("docker logs -f "+get_cid())

def exec_bash():
    nopipe("docker exec -it "+get_cid()+" bash")

def main():
    load_conf()

    a1 = sys.argv[1]

    if not os.path.exists(ENVDIR):
        os.makedirs(ENVDIR)

    if(a1=='build'):
        build_image()
    elif(a1=='run'):
        run(ENV)
    elif(a1=='start'):
        start_container()
    elif(a1=='stop'):
        stop_container()
    elif(a1=='clean'):
        clean()
    elif(a1=='logs'):
        logs()
    elif(a1=='bash'):
        exec_bash()
    elif(a1=='genconf'):
        generate_nginx_conf()
    elif(a1=='ndeploy'):
        ndeploy()
    elif(a1=='nclean'):
        clean_nginx()
    else:
        print ("Unrecognized command")

if __name__== "__main__":
    main()

