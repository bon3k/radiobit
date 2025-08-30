## Manual Build Instructions (Radiobit)

### 1. Flash Raspberry Pi OS Lite

* Use Raspberry Pi Imager.
* Set the **hostname** and **username** to `radiobit`.
* Choose any password.
* (Optional) Configure Wi-Fi and enable **SSH** during setup.

### 2. Hardware Setup

* Insert the SD card into the Raspberry Pi.
* Mount the **LCD HAT** and **PiSugar3 module**.

### 3. Connect to the Raspberry Pi

Boot the Raspberry Pi and connect via SSH:

```bash
ssh radiobit@radiobit.local
```

### 4. System Update

Run:

```bash
sudo apt-get update && sudo apt-get upgrade -y && sudo apt-get dist-upgrade -y
```

### 5. Enable SPI and I2C

Run:

```bash
sudo raspi-config
```

Go to **Interface Options** and enable **SPI** and **I2C**.

### 6. Configure LCD Display

Edit /boot/firmware/config.txt and add the following line at the end of the file:

```ini
dtoverlay=waveshare-1-3inch-lcd-color
```

To open the file in a text editor, run:

```bash
sudo nano /boot/firmware/config.txt
```

### 7. Install PiSugar Power Manager

```bash
wget https://github.com/PiSugar/pisugar-power-manager-rs/releases/download/v2.0.0/pisugar-server_2.0.0-1_arm64.deb
wget https://github.com/PiSugar/pisugar-power-manager-rs/releases/download/v2.0.0/pisugar-poweroff_2.0.0-1_arm64.deb
```

```bash
sudo apt install ./pisugar-server_2.0.0-1_arm64.deb
sudo apt install ./pisugar-poweroff_2.0.0-1_arm64.deb
```

### 8. Clone the Radiobit Repository

```bash
git clone https://github.com/bon3k/radiobit.git
cd radiobit
```

### 9. Copy Stream Directory

```bash
cp -r stream /home/radiobit/
```

### 10. Make the scripts executable

```bash
chmod +x /home/radiobit/stream/main.py
chmod +x /home/radiobit/stream/web_app/app.py
chmod +x /home/radiobit/stream/stream.sh
chmod +x /home/radiobit/stream/set_volume.sh
```

### 11. Install System Services

```bash
sudo cp stream.service /etc/systemd/system/
sudo cp gunicorn.service /etc/systemd/system/
```

### 12. Install and Configure Nginx

```bash
sudo apt install nginx -y
sudo systemctl start nginx
sudo systemctl enable nginx
sudo cp radiobit.conf /etc/nginx/sites-available/
sudo ln -s /etc/nginx/sites-available/radiobit.conf /etc/nginx/sites-enabled/
```

### 13. Install System Dependencies

```bash
sudo apt install mpv libmpv-dev python3-pip pipewire pipewire-audio-client-libraries
```

### 14. Set Up Python Environment

```bash
python3 -m venv ~/radioenv
source ~/radioenv/bin/activate
pip install -r requirements.txt
```

### 15. Configure Sudoers for Volume Control

The set_volume.sh script needs to run with elevated privileges, but Radiobit requires it to work without asking for a password each time.
To allow this, add the following line to the sudoers file:

Open the editor with:

```bash
sudo visudo
```

At the end of the file, append:

```ini
radiobit ALL=(ALL) NOPASSWD: /home/radiobit/stream/set_volume.sh *

```

### 16. Enable Services and Restart

```bash
sudo systemctl enable stream.service
sudo systemctl enable gunicorn.service
sudo systemctl restart nginx
sudo reboot
```

---

This guide assumes you are logged in as user `radiobit` on your Raspberry Pi.

