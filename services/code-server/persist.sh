#!/bin/sh
# Runs as the coder user at every container start (code-server's entrypoint.d).
mkdir -p "$HOME/.config/git" "$HOME/.local/bin"
# ~/.ssh is a persisted bind mount; ssh refuses keys if the dir is open to others
mkdir -p "$HOME/.ssh" && chmod 700 "$HOME/.ssh"
