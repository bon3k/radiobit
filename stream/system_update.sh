#!/bin/bash

LOG="/tmp/system_update.log"
LOCK="/tmp/system_update.lock"

echo "=== $(date) ===" >> "$LOG"

# Evitar ejecuciones simultáneas
if [ -f "$LOCK" ]; then
  echo "$(date): Update ya en curso" >> "$LOG"
  exit 1
fi

touch "$LOCK"
trap "rm -f $LOCK" EXIT

echo "$(date): Iniciando system update (user: $(whoami))" >> "$LOG"

export DEBIAN_FRONTEND=noninteractive

# Update
echo "$(date): apt update" >> "$LOG"
apt update >> "$LOG" 2>&1

# Upgrade
echo "$(date): apt dist-upgrade" >> "$LOG"
apt dist-upgrade -y >> "$LOG" 2>&1

RET=$?

echo "$(date): exit code = $RET" >> "$LOG"

exit $RET
