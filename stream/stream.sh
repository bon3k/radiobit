#!/bin/bash

set -e

source /home/radiobit/radioenv/bin/activate
exec python3 /home/radiobit/stream/main.py
