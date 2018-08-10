#!/bin/bash
P_DIR="/usr/local/lib/docker-server-manager"
X_DESTINATION="/usr/local/bin/dserver"

if [ -d "$P_DIR" ]
then
    rm -r "$P_DIR"
fi
git clone --depth 1 https://github.com/jrlangford/docker-server-manager.git $P_DIR
ln -sf $P_DIR/server.py $X_DESTINATION
