#!/usr/bin/env python3.6
import subprocess
import sys
import os
import secrets
import json
import argparse
from pathlib import Path
from shutil import copyfile, rmtree
from jinja2 import Template
from collections import namedtuple

ENV=None
REPOSITORY_NAME=None
DEFAULT_MOUNTBASE=None
NGINX_DYN_CONF_DIR=None
IMAGE_NAME=None
BUILD_ENABLED=True
ENVDIR=None
CIDFILE=None
SECRET_KEY_FILE=None
NGINX_CONF_LOCATION_FILE=None

NGINX_TEMPLATE='nginx.conf.jn2'
DOCKERIGNORE_BASEFILE=".dockerignore_base"

SERVER_MAP = None
VOLUMES=None

def load_conf(conf):
    global ENV
    global REPOSITORY_NAME
    global DEFAULT_MOUNTBASE
    global NGINX_DYN_CONF_DIR
    global SERVER_MAP
    global VOLUMES
    global IMAGE_NAME

    global BUILD_ENABLED
    global LISTEN_PORT
    global ENVDIR
    global CIDFILE
    global SECRET_KEY_FILE
    global NGINX_CONF_LOCATION_FILE

    c = None

    cfile = conf.file

    # conf.environment overrides conf.file value
    if conf.environment != None:
        cfile = "serverconf.{}.json".format(conf.environment)

    with open(cfile,'r') as f:
        c =  f.read().rstrip()
    jconf = json.loads(c)

    ENV=jconf['env']
    REPOSITORY_NAME=jconf['repository_name']
    DEFAULT_MOUNTBASE = jconf['default_mountbase']
    NGINX_DYN_CONF_DIR=jconf['nginx_dyn_conf_dir']
    SERVER_MAP = jconf['server_map']
    VOLUMES = jconf['volumes']

    ENVDIR = '.dcm_env_'+ENV
    CIDFILE=ENVDIR+"/cidfile"
    SECRET_KEY_FILE=ENVDIR+"/s_key"
    NGINX_CONF_LOCATION_FILE=ENVDIR+"/nginx_conf_location"

    allowed_host_keywords = ["pwd", "default", ""]
    for v in VOLUMES:
        mountpoint = v.get('host', "")
        if not (os.path.isabs(mountpoint) or mountpoint in allowed_host_keywords) :
            sys.exit("Failed, please provide absolute paths for all volume mountpoints or use a valid keyword")

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

def get_volume_mountpoint(volume):
    m = namedtuple('path', 'type')

    if 'host' in volume:
        if volume['host'] == 'default':
            m.path = "{}/{}_{}".format(DEFAULT_MOUNTBASE, REPOSITORY_NAME ,volume['tag'])
            m.type = "host"
        elif volume['host'] == 'pwd':
            m.path = os.getcwd()
            m.type = "host"
        else:
            m.path = volume['host']
            m.type = "host"
    else:
        m.path = volume['tag']
        m.type = "docker"

    return m

def generate_dockerignore():
    dockerignore_file = ".dockerignore"

    untracked_files = None

    c = Path(DOCKERIGNORE_BASEFILE)
    if  c.is_file():
        copyfile(DOCKERIGNORE_BASEFILE, dockerignore_file)
    else:
        untracked_files = ".git*\n.dockerignore\n"

    untracked_files += pipe("git ls-files --others")

    with open(dockerignore_file,'w') as f:
        f.write(untracked_files)

def get_container_name():
    return pipe("docker inspect --format='{{.Name}}' "+get_cid()).lstrip("/")

def get_volume_mountpoint_from_tag(tag):
    for v in VOLUMES:
        if v["tag"] == tag:
            return get_volume_mountpoint(v)

def generate_nginx_conf():
    text = None
    with open(NGINX_TEMPLATE,'r') as f:
        text = f.read()

    portsString = pipe("docker inspect --format='{{json .NetworkSettings.Ports}}' "+get_cid())
    forwarded_ports = json.loads(portsString)

    servers = SERVER_MAP

    mapped_servers = []

    for s in servers:
        container_port = s['c_port']
        host_port = forwarded_ports[container_port][0]['HostPort']
        ms = s.copy()
        ms.update(
            {
                "h_port":host_port,
                "mapped_volumes":[]
            }
        )
        if "l_port" not in s:
            ms.update(
                {
                    "l_port":80
                }
            )
        for volume in s.get('volumes_served', []):
            mountpoint = get_volume_mountpoint_from_tag(volume['tag'])
            if mountpoint.type == 'docker':
                print("Warning: cannot serve unmounted docker volume: "+mountpoint.path)
                continue
            if not os.path.exists(mountpoint.path):
                print("Warning: cannot serve unexistent path: "+mountpoint.path)
                continue

            mv = volume.copy()
            mv.update(
                {
                    "host_dir":mountpoint.path
                }
            )
            ms['mapped_volumes'].append(mv)

        mapped_servers.append(ms)

    t = Template(text)
    o = t.render(
        servers = mapped_servers,
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
        generate_dockerignore()
        command = "docker build -t {} .".format(IMAGE_NAME)
        nopipe(command)

def create_host_mountpoints():
    for v in VOLUMES:
        mountpoint = get_volume_mountpoint(v)
        if mountpoint.type != "docker" and not os.path.exists(mountpoint.path):
            os.makedirs(mountpoint.path)

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

    create_host_mountpoints()

    volstring = ""
    for v in VOLUMES:
        mountpoint = get_volume_mountpoint(v)
        volstring+="--volume={}:{} ".format(mountpoint.path, v['cont'])

    command = " \
        docker run -d -P \
            --name={} \
            --env-file={} \
            --env='S_KEY={}' \
            {} \
            --cidfile={} \
            {}".format(
            container_name,
            envfile,
            secret_key,
            volstring,
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

def inspect_container():
    nopipe("docker inspect "+get_cid())

def remove_container():
    nopipe("docker rm "+get_cid())

def should_clean_volume(volume):
    # Returns true only if `auto_clean` is set to True and current directory is not mounted
    return volume.get('auto_clean', False) and volume.get('host') != 'pwd'

def clean_marked_volumes():
    start_container()
    for v in VOLUMES:
        if should_clean_volume(v):
            command = "docker exec {} /bin/sh -c 'rm -rf {}/*'".format(
                get_cid(),
                v['cont']
            )
            nopipe(command)

def clean_marked_mountpoints():
    for v in VOLUMES:
        if should_clean_volume(v):
            m = get_volume_mountpoint(v)
            if m.type == "host":
                rmtree(m.path)
            elif m.type == "docker":
                nopipe("docker volume rm {}".format(m.path))

def clean():
    p = Path(NGINX_CONF_LOCATION_FILE)
    if p.is_file():
        sys.exit("Failed, clean nginx installation with './server.py nclean' before proceeding.")
    clean_marked_volumes()
    stop_container()
    remove_container()
    clean_marked_mountpoints()
    rmtree(ENVDIR)

def logs():
    nopipe("docker logs -f "+get_cid())

def exec_bash():
    nopipe("docker exec -it "+get_cid()+" bash")

def main():
    parser = argparse.ArgumentParser(description='Easily build and deploy docker images')
    parser.add_argument('command', action="store")

    source_opts = parser.add_mutually_exclusive_group()

    source_opts.add_argument(
        '-f', action="store", dest="file",
        help="Set serverconf file to be used", default='serverconf.json'
    )

    source_opts.add_argument(
        '-e', action="store", dest="environment",
        help="Set serverconf env to be used", default=None
    )


    p = parser.parse_args()

    load_conf(p)

    a1 = p.command

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
    elif(a1=='inspect'):
        inspect_container()
    else:
        print ("Unrecognized command")

if __name__== "__main__":
    main()

