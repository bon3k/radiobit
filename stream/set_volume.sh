#!/bin/bash
# set_volume.sh - aplicar volumen en vivo y guardar persistencia

VOL="$1"
USER="radiobit"
USER_ID=$(id -u "$USER")
WPCTL="/usr/bin/wpctl"
CONF_DIR="/home/$USER/.config/wireplumber/wireplumber.conf.d"
CONF_FILE="$CONF_DIR/10-default-volume.conf"
LOG="/tmp/set_volume.log"

if [ -z "$VOL" ]; then
  echo "$(date): Error - no se proporcionó volumen" >> "$LOG"
  exit 2
fi

# validar número
awk -v vol="$VOL" 'BEGIN {if(vol+0<0 || vol+0>1) exit 1}' || {
  echo "$(date): Error - volumen fuera de rango ($VOL)" >> "$LOG"
  exit 3
}

echo "=== $(date) ===" >> "$LOG"
echo "Llamado con VOL=$VOL (ejecutando script como $(whoami))" >> "$LOG"

# Guardar persistencia
mkdir -p "$CONF_DIR"
cat > "$CONF_FILE" <<EOF
[alsa-monitor]
default-volume = $VOL
EOF
echo "$(date): guardado persistente en $CONF_FILE" >> "$LOG"

# Forzar entorno de la sesion del usuario objetivo
export XDG_RUNTIME_DIR="/run/user/$USER_ID"
export DBUS_SESSION_BUS_ADDRESS="unix:path=${XDG_RUNTIME_DIR}/bus"

echo "$(date): XDG_RUNTIME_DIR=$XDG_RUNTIME_DIR" >> "$LOG"
echo "$(date): DBUS_SESSION_BUS_ADDRESS=$DBUS_SESSION_BUS_ADDRESS" >> "$LOG"
echo "$(date): WPCTL=$WPCTL" >> "$LOG"

# Ejecutar wpctl como usuario
sudo -u "$USER" env XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
    DBUS_SESSION_BUS_ADDRESS="$DBUS_SESSION_BUS_ADDRESS" \
    "$WPCTL" set-volume @DEFAULT_AUDIO_SINK@ "$VOL" >> "$LOG" 2>&1
RET=$?

echo "$(date): wpctl exit code = $RET" >> "$LOG"

sudo -u "$USER" env XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
    DBUS_SESSION_BUS_ADDRESS="$DBUS_SESSION_BUS_ADDRESS" \
    "$WPCTL" get-volume @DEFAULT_AUDIO_SINK@ >> "$LOG" 2>&1 || true

exit $RET
