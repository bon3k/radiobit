## Instrucciones para construir Radiobit manualmente

### 1. Flashear Raspberry Pi OS Lite

* Usa Raspberry Pi Imager.
* Establece `radiobit` como **nombre de host** y **usuario**.
* Elige cualquier contraseña.
* (Opcional) Configura la conexión Wi-Fi y activa **SSH** durante la configuración.

### 2. Montaje del hardware

* Inserta la tarjeta SD en la Raspberry Pi.
* Conecta el **HAT LCD** y el **módulo PiSugar3**.

### 3. Connectate a  Raspberry Pi

arranca Raspberry Pi y conectate via SSH:

```bash
ssh radiobit@radiobit.local
```

### 4. Actualizar el sistema

Inicia la Raspberry Pi y ejecuta:

```bash
sudo apt-get update && sudo apt-get upgrade -y && sudo apt-get dist-upgrade -y
```

### 5. Activar SPI e I2C

Ejecuta:

```bash
sudo raspi-config
```

Ve a **Opciones de interfaz** y activa **SPI** e **I2C**.

### 6. Configure LCD Display

Edita /boot/firmware/config.txt y añade la suguiente linea al final del archivo:

```ini
dtoverlay=waveshare-1-3inch-lcd-color
```

Para abrir un editor de texto:

```bash
sudo nano /boot/firmware/config.txt
```

### 7. Instalar el gestor de energía de PiSugar

```bash
wget https://github.com/PiSugar/pisugar-power-manager-rs/releases/download/v2.0.0/pisugar-server_2.0.0-1_arm64.deb
wget https://github.com/PiSugar/pisugar-power-manager-rs/releases/download/v2.0.0/pisugar-poweroff_2.0.0-1_arm64.deb
```

```bash
sudo apt install ./pisugar-server_2.0.0-1_arm64.deb
sudo apt install ./pisugar-poweroff_2.0.0-1_arm64.deb
```

### 8. Clonar el repositorio de Radiobit

```bash
git clone https://github.com/bon3k/radiobit.git
cd radiobit
```

### 9. Copiar el directorio `stream`

```bash
cp -r stream /home/radiobit/
```

### 10. Haz ejecutables los scripts

```bash
chmod +x /home/radiobit/stream/main.py
chmod +x /home/radiobit/stream/web_app/app.py
```

### 11. Instalar los archivos de servicio

```bash
sudo cp stream.service /etc/systemd/system/
sudo cp gunicorn.service /etc/systemd/system/
```

### 12. Instalar y Configurar Nginx

```bash
sudo apt install nginx -y
sudo systemctl start nginx
sudo systemctl enable nginx
sudo cp radiobit.conf /etc/nginx/sites-available/
sudo ln -s /etc/nginx/sites-available/radiobit.conf /etc/nginx/sites-enabled/
```

### 13. Instalar dependencias del sistema

```bash
sudo apt install mpv libmpv-dev python3-pip pipewire pipewire-audio-client-libraries
```

### 14. Crear entorno virtual e instalar dependencias Python

```bash
python3 -m venv ~/radioenv
source ~/radioenv/bin/activate
pip install -r requirements.txt
```

### 15. Habilitar servicios y reiniciar

```bash
sudo systemctl enable stream.service
sudo systemctl enable gunicorn.service
sudo systemctl restart nginx
sudo reboot
```

---

Esta guía asume que has iniciado sesión como el usuario `radiobit` en tu Raspberry Pi.

