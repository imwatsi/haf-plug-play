#!/bin/bash

# stop current process
pkill -SIGINT "plug_play"
sleep 10
pkill -SIGKILL "plug_play"

# run SQL reset script
psql -U postgres -d haf -f reset.sql

# restart Plug & Play
haf_plug_play