#!/bin/bash
P_DIR="docker-server-manager"

git clone https://github.com/jrlangford/docker-server-manager.git

cp $P_DIR/server.py .
chmod +x $P_DIR/server.py

cp $P_DIR/serverconf.example.json serverconf.json
cp $P_DIR/nginx.conf.jn2 .

rm -rf $P_DIR

rm -- "$0"
