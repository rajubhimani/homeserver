#!/bin/sh
# Runs as the coder user at every container start (code-server's entrypoint.d).
# /home/coder is a bind mount, so it starts empty and hides the image's default
# dotfiles: copy them in from /etc/skel, never overwriting anything that exists.
cp -n /etc/skel/.[!.]* "$HOME"/ 2>/dev/null
mkdir -p "$HOME/.local/bin"
# ssh refuses keys if the dir is open to others
mkdir -p "$HOME/.ssh" && chmod 700 "$HOME/.ssh"
exit 0
