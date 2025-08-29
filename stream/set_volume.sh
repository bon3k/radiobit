#!/bin/bash
# Script para cambiar el volumen por defecto de WirePlumber
# $1 -> volumen entre 0.0 y 1.0

VOLUME_FILE="/usr/share/wireplumber/main.lua.d/40-device-defaults.lua"
VOL="$1"

# Validar que sea un número entre 0 y 1
awk -v vol="$VOL" 'BEGIN {if(vol<0 || vol>1) exit 1}' || exit 1

# Reemplazar la línea del default-volume
sudo sed -i "s/\(\[\"default-volume\"\]\s*=\s*\).*/\1$VOL,/" "$VOLUME_FILE"

# Recargar WirePlumber sin reiniciar toda la Raspberry
# Se usa sudo -u radiobit para ejecutar en la sesión de usuario correcta
sudo -u radiobit DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$(id -u radiobit)/bus" \
    systemctl --user restart wireplumber

