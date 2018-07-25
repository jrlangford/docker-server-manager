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
IMAGE_NAME=None
BUILD_ENABLED=True

ENVDIR = 'environment'
CIDFILE=ENVDIR+"/cidfile"
SECRET_KEY_FILE=ENVDIR+"/s_key"
STATIC_DIR_FILE=ENVDIR+"/static_dir"
NGINX_TEMPLATE='nginx.conf.jn2'
NGINX_CONF_LOCATION_FILE=ENVDIR+"/nginx_conf_location"

SERVER_MAP = None

def load_conf():
    global ENV
    global REPOSITORY_NAME
    global CONTAINER_STATIC_DIR
    global HOST_STATIC_DIR
    global NGINX_DYN_CONF_DIR
    global SERVER_MAP
    global IMAGE_NAME

    global BUILD_ENABLED

    c = None
    with open('serverconf.json','r') as f:
        c =  f.read().rstrip()
    jconf = json.loads(c)

    ENV=jconf['env']
    REPOSITORY_NAME=jconf['repository_name']
    CONTAINER_STATIC_DIR=jconf['container_static_dir']
    HOST_STATIC_DIR=jconf['host_static_dir']
    NGINX_DYN_CONF_DIR=jconf['nginx_dyn_conf_dir']
    SERVER_MAP = jconf['server_map']

    if "external_image_name" in jconf:
        IMAGE_NAME=jconf["external_image_name"]
        BUILD_ENABLED=False
    else:
        githash = pipe("git rev-parse --short HEAD")
        tag = get_version()+'-'+githash
        IMAGE_NAME = REPOSITORY_NAME+':'+tag


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
    forwarded_ports = json.loads(portsString)

    v_servers = SERVER_MAP
    for s in v_servers:
        container_port = s['c_port']
        host_port = forwarded_ports[container_port][0]['HostPort']
        s.update(
            {
                "h_port":host_port
            }
        )

    t = Template(text)
    o = t.render(
        v_servers = v_servers,
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
    nopipe("sudo nginx -t")

def read_nginx_conf_location():
    with open(NGINX_CONF_LOCATION_FILE,'r') as f:
        return f.read().rstrip()

def reload_nginx_conf():
    nopipe("sudo nginx -s reload")

def clean_nginx():
    os.remove(read_nginx_conf_location())
    test_nginx_conf()
    reload_nginx_conf()
    os.remove(NGINX_CONF_LOCATION_FILE)

# Note: Deployment of only one environment at a time is supported
def deploy_nginx():
    generate_nginx_conf()
    copy_nginx_conf()
    test_nginx_conf()
    reload_nginx_conf()

def build_image():
    if BUILD_ENABLED:
        command = "docker build -t {} .".format(IMAGE_NAME)
        nopipe(command)

def run():
    env = ENV
    if(env is None):
        sys.exit("Failed, missing environment parameter")

    if not os.path.exists(ENVDIR):
        os.makedirs(ENVDIR)

    envfile="."+env+".env"

    e = Path(envfile)
    if not e.is_file():
        sys.exit(envfile+" not found")

    c = Path(CIDFILE)
    if c.is_file():
        sys.exit("Failed, CIDFILE present: "+CIDFILE)

    command = "docker images -q "+IMAGE_NAME
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
        docker run -d -P \
            --name={} \
            --env-file={} \
            --env='S_KEY={}' \
            --volume={}:{} \
            --cidfile={} \
            {}".format(
            container_name,
            envfile,
            secret_key,
            static_dir,
            CONTAINER_STATIC_DIR,
            CIDFILE,
            IMAGE_NAME
        )

    nopipe(command)

def deploy():
    run()
    deploy_nginx()

def dismiss():
    clean_nginx()
    clean()

def reload_container():
    dismiss()
    deploy()

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
        sys.exit("Failed, clean nginx installation with './server.py nclean' before proceeding.")
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

    if(a1=='build'):
        build_image()
    elif(a1=='run'):
        run()
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
        deploy_nginx()
    elif(a1=='nclean'):
        clean_nginx()
    elif(a1=='dismiss'):
        dismiss()
    elif(a1=='deploy'):
        deploy()
    elif(a1=='reload'):
        reload_container()
    else:
        print ("Unrecognized command")

if __name__== "__main__":
    main()

