import spidev
import asyncio
import time
import RPi.GPIO as GPIO
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import sugarpie
import zlib

class InterfazLCD:
    def __init__(self, rst_pin=27, dc_pin=25, bl_pin=24, cs_pin=8):
        self.width = 240
        self.height = 240
        self.RST_PIN = rst_pin
        self.DC_PIN = dc_pin
        self.BL_PIN = bl_pin
        self.CS_PIN = cs_pin
        self.spi = spidev.SpiDev()
        self.last_image_hash = None
        self.ultimo_tiempo_mostrado = -1
        self.pisugar = sugarpie.Pisugar()
        self.last_input_time = time.time()
        self.inactive_timeout = 60  # segundos
        self.backlight_on = True
        self.ultimo_nivel_bateria = -1
        self.current_image = None # flag para guardar imagen y actualizar bateria modo stream
        self.scroll_offset = 0
        self.last_scroll_time = time.time()



        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        for pin in (self.RST_PIN, self.DC_PIN, self.BL_PIN, self.CS_PIN):
            GPIO.setup(pin, GPIO.OUT)

        GPIO.setup(self.BL_PIN, GPIO.OUT)

        # Iniciar PWM en BL_PIN con una frecuencia de 1000 Hz
        self.bl_pwm = GPIO.PWM(self.BL_PIN, 1000)
        self.bl_pwm.start(100)  # Brillo al 100%
        self.spi.open(0, 0)
        self.spi.max_speed_hz = 32000000
        self.spi.mode = 0b00
        self.inicializar_lcd()

    def __del__(self):
        self.spi.close()
        GPIO.cleanup()

    def start_inactivity_monitor(self):
        # crear la tarea de monitorización solo cuando se llame a este método
        asyncio.create_task(self.monitor_inactivity())

    async def monitor_inactivity(self):
        while True:
            await asyncio.sleep(5)
            if self.backlight_on and time.time() - self.last_input_time > self.inactive_timeout:
                self.bl_pwm.ChangeDutyCycle(0)
                self.backlight_on = False

    def update_activity(self):
        self.last_input_time = time.time()
        if not self.backlight_on:
            self.bl_pwm.ChangeDutyCycle(100)
            self.backlight_on = True

    def write_command(self, cmd):
        GPIO.output(self.DC_PIN, GPIO.LOW)
        self.spi.xfer([cmd])

    def write_data(self, data):
        GPIO.output(self.DC_PIN, GPIO.HIGH)
        self.spi.xfer(data)

    def set_window(self, x_start=0, y_start=0, x_end=239, y_end=239):
        self.write_command(0x2A)
        self.write_data([0x00, x_start, 0x00, x_end])
        self.write_command(0x2B)
        self.write_data([0x00, y_start, 0x00, y_end])
        self.write_command(0x2C)

    def inicializar_lcd(self):
        GPIO.output(self.RST_PIN, GPIO.HIGH)
        time.sleep(0.1)
        GPIO.output(self.RST_PIN, GPIO.LOW)
        time.sleep(0.1)
        GPIO.output(self.RST_PIN, GPIO.HIGH)

        comandos = [
            (0x36, [0x00]), (0x3A, [0x05]), (0xB2, [0x0C, 0x0C, 0x00, 0x33, 0x33]),
            (0xB7, [0x35]), (0xBB, [0x1F]), (0xC0, [0x2C]), (0xC2, [0x01]),
            (0xC3, [0x12]), (0xC4, [0x20]), (0xC6, [0x0F]), (0xD0, [0xA4, 0xA1]),
            (0xE0, [0xD0, 0x08, 0x11, 0x08, 0x0C, 0x15, 0x39, 0x33, 0x50, 0x36, 0x13, 0x14, 0x29, 0x2D]),
            (0xE1, [0xD0, 0x08, 0x10, 0x08, 0x06, 0x06, 0x39, 0x44, 0x51, 0x0B, 0x16, 0x14, 0x2F, 0x31])
        ]

        for cmd, data in comandos:
            self.write_command(cmd)
            self.write_data(data)

        self.write_command(0x21)
        self.write_command(0x11)
        self.write_command(0x29)

    def display_image(self, image):
        if isinstance(image, str):
            img = Image.open(image)
        else:
            img = image

        img = img.rotate(180, expand=False)  #     //// ROTAR PANTALLA ///// horizontal: 270
        img = img.resize((240, 240)).convert("RGB")
        self.current_image = img.copy()  # <--- Guarda copia
        img_data = np.array(img, dtype=np.uint16)
        # check image hash
        current_hash = zlib.crc32(img.tobytes())
        if current_hash == self.last_image_hash:
            return
        self.last_image_hash = current_hash

        r = (img_data[:, :, 0] >> 3) << 11
        g = (img_data[:, :, 1] >> 2) << 5
        b = (img_data[:, :, 2] >> 3)
        img_rgb565 = (r | g | b).astype(np.uint16).byteswap().tobytes()

        self.set_window()
        for i in range(0, len(img_rgb565), 4096):
            self.write_data(img_rgb565[i:i + 4096])

    def split_text(self, texto, max_length=14):
        return [texto[i:i+max_length] for i in range(0, len(texto), max_length)]

    def update_battery_icon_only(self):
        """
        Dibuja solo el icono de batería encima de la imagen actual.
        """
        if self.current_image is None:
            return  # no hay imagen base para mostrar encima

        # usa la imagen actual como fondo
        base = self.current_image.copy()
        draw = ImageDraw.Draw(base)

        # dibujar el icono encima del fondo actual
        self.draw_battery_icon(draw)

        # coordenadas del icono de bateria
        x, y = 200, 10
        ancho = 25
        alto = 13

        # cortar solo el area del icono
        icon_crop = base.crop((x, y, x + ancho, y + alto))

        icon_crop = icon_crop.rotate(180, expand=False)

        # ajustar coordenadas segun la rotación
        x_rotado = 240 - (x + ancho)
        y_rotado = 240 - (y + alto)

        # convertir a RGB565
        img_data = np.array(icon_crop, dtype=np.uint16)
        r = (img_data[:, :, 0] >> 3) << 11
        g = (img_data[:, :, 1] >> 2) << 5
        b = (img_data[:, :, 2] >> 3)
        img_rgb565 = (r | g | b).astype(np.uint16).byteswap().tobytes()

        # dibujar solo esa region en pantalla
        self.set_window(x_rotado, y_rotado, x_rotado + ancho - 1, y_rotado + alto - 1)
        self.write_data(img_rgb565)


    def draw_battery_icon(self, draw):
        x, y = 200, 10  # posicion icono bateria
        ancho = 24
        alto = 12
        borde = 2
        relleno_max = ancho - 6

        nivel = self.get_battery_level()
        nivel = max(0, min(nivel, 100))

        # marco del icono
        draw.rectangle((x, y, x + ancho, y + alto), outline="grey", fill="black")

        # terminal del icono
        draw.rectangle((x + ancho, y + alto // 4, x + ancho + 2, y + 3 * alto // 4), outline="grey", fill="grey")

        # nivel de bateria
        relleno = (relleno_max * nivel) // 100
        if relleno > 0:
            draw.rectangle((x + 3, y + 3, x + 3 + relleno, y + alto - 3), fill="grey")

    def get_battery_level(self):
        now = time.time()
        if now - getattr(self, "_last_battery_check", 0) > 10:
            try:
                self.ultimo_nivel_bateria = self.pisugar.get_battery_level()
            except:
                self.ultimo_nivel_bateria = 0
            self._last_battery_check = now
        return self.ultimo_nivel_bateria

    def draw_volume_triangle(self, draw, volume_level):

        # posicion base en la pantalla
        x = 10
        y = 10
        height = 14
        width = 8

        # dibuja el altavoz
        altavoz = [
            (x + width, y),
            (x + width, y + height),
            (x, y + height - 4),
            (x, y + 4)
        ]
        draw.polygon(altavoz, fill="grey")

        # dibuja ondas de sonido
        if volume_level > 0:
            draw.arc([x + width + 2, y + 2, x + width + 6, y + height - 2], start=300, end=60, fill="grey")
        if volume_level > 10:
            draw.arc([x + width + 3, y + 1, x + width + 8, y + height - 1], start=300, end=60, fill="grey")
        if volume_level > 20:
            draw.arc([x + width + 4, y, x + width + 10, y + height], start=300, end=60, fill="grey")
        if volume_level > 30:
            draw.arc([x + width + 5, y - 1, x + width + 12, y + height + 1], start=300, end=60, fill="grey")
        if volume_level > 40:
            draw.arc([x + width + 6, y - 2, x + width + 14, y + height + 2], start=300, end=60, fill="grey")
        if volume_level > 50:
            draw.arc([x + width + 7, y - 3, x + width + 16, y + height + 3], start=300, end=60, fill="grey")
        if volume_level > 60:
            draw.arc([x + width + 8, y - 4, x + width + 18, y + height + 4], start=300, end=60, fill="grey")
        if volume_level > 70:
            draw.arc([x + width + 9, y - 5, x + width + 20, y + height + 5], start=300, end=60, fill="grey")
        if volume_level > 80:
            draw.arc([x + width + 10, y - 6, x + width + 22, y + height + 6], start=300, end=60, fill="grey")
        if volume_level > 90:
            draw.arc([x + width + 11, y - 7, x + width + 24, y + height + 7], start=300, end=60, fill="grey")


    def draw_text_on_lcd(self, texto, extra_info=None, progreso_barra=None, volume_level=None):
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 19)
        img = Image.new("RGB", (240, 240), "black")
        draw = ImageDraw.Draw(img)

        max_width = 220  # 240 - 10 (izquierda) - 10 (derecha)
        margin_x = 10
        y = 75
        line_height = draw.textbbox((0, 0), "A", font=font)[3]

        # romper texto en lineas sin exceder el ancho maximo
        words = texto.split()
        lines = []
        current_line = ""
        for word in words:
            prueba_linea = f"{current_line} {word}".strip()
            bbox = draw.textbbox((0, 0), prueba_linea, font=font)
            if bbox[2] - bbox[0] <= max_width:
                current_line = prueba_linea
            else:
                lines.append(current_line)
                current_line = word
        if current_line:
            lines.append(current_line)

        for line in lines[:4]:  # máximo 4 líneas
            bbox = draw.textbbox((0, 0), line, font=font)
            x = max((240 - (bbox[2] - bbox[0])) // 2, margin_x)
            draw.text((x, y), line, fill="lightgrey", font=font)
            y += line_height

        if extra_info:
            draw.text((65, 180), extra_info, font=font, fill=(200, 200, 200))

        if progreso_barra is not None:
            ancho_barra = 200
            altura_barra = 10
            x_inicio = 20
            y_inicio = 215
            draw.rectangle([x_inicio, y_inicio, x_inicio + ancho_barra, y_inicio + altura_barra], outline="lightgrey", width=1)
            draw.rectangle([x_inicio, y_inicio, x_inicio + progreso_barra, y_inicio + altura_barra], fill=(0, 255, 0))

        self.draw_battery_icon(draw)
        if volume_level is not None:
            self.draw_volume_triangle(draw, volume_level)
        return img


    def display_mp3_info(self, titulo, tiempo_actual, duracion, volume_level=None):
        titulo = titulo.replace('_', ' ').replace('-', ' ')

        if int(tiempo_actual) == self.ultimo_tiempo_mostrado:
            return
        self.ultimo_tiempo_mostrado = int(tiempo_actual)

        lineas_titulo = self.split_text(titulo, max_length=17)
        titulo_procesado = "\n".join(lineas_titulo[:4])

        tiempo_str = f"{int(tiempo_actual // 60)}:{int(tiempo_actual % 60):02d}"
        duracion_str = f"{int(duracion // 60)}:{int(duracion % 60):02d}"
        extra_info = f"{tiempo_str} / {duracion_str}"

        progreso = int((tiempo_actual / duracion) * 200) if duracion > 0 else 0
        img = self.draw_text_on_lcd(titulo, extra_info, progreso, volume_level)
        self.display_image(img)

    async def display_menu(self, opciones, seleccion_index, titulo=None):
        width, height = self.width, self.height
        max_items_pantalla = height // 20 - (1 if titulo else 0)
        max_width = width - 10

        try:
            fuente = ImageFont.truetype("DejaVuSans.ttf", 16)
        except IOError:
            fuente = ImageFont.load_default()

        scroll_offset = 0
        scroll_start_time = None
        scroll_done = False
        scroll_delay = 0.4
        last_index = -1
        last_render_time = 0

        # indice del primer item visible
        primer_visible = max(0, seleccion_index - max_items_pantalla + 1)

        while True:
            ahora = time.time()
            redibujar = seleccion_index != last_index or ahora - last_render_time > scroll_delay

            if redibujar:
                imagen = Image.new("RGB", (width, height), "black")
                draw = ImageDraw.Draw(imagen)

                y = 0
                if titulo:
                    draw.text((5, y), titulo[:width // 10], font=fuente, fill="white")
                    y += 23

                scroll_needed = False
                texto_seleccionado_ancho = 0

                for i in range(primer_visible, min(primer_visible + max_items_pantalla, len(opciones))):
                    opcion = opciones[i]
                    bbox = draw.textbbox((0, 0), opcion, font=fuente)
                    texto_ancho = bbox[2] - bbox[0]

                    if i == seleccion_index:
                        draw.rectangle([(0, y), (width, y + 20)], fill="lightgray")

                        if texto_ancho > max_width:
                            scroll_needed = True
                            if seleccion_index != last_index:
                                scroll_offset = 0
                                scroll_start_time = ahora
                                scroll_done = False

                            if scroll_start_time is None:
                                scroll_start_time = ahora

                            tiempo_scroll = ahora - scroll_start_time - 0.5
                            if tiempo_scroll > 0 and not scroll_done:
                                velocidad_scroll = 40
                                scroll_offset = int(tiempo_scroll * velocidad_scroll)
                                max_scroll = texto_ancho - max_width + 10
                                if scroll_offset >= max_scroll:
                                    scroll_offset = max_scroll
                                    scroll_done = True
                            offset_x = 5 - scroll_offset
                        else:
                            scroll_offset = 0
                            scroll_start_time = None
                            scroll_done = True
                            offset_x = 5

                        draw.text((offset_x, y), opcion, font=fuente, fill="black")
                    else:
                        if texto_ancho > max_width:
                            for j in range(len(opcion), 0, -1):
                                truncado = opcion[:j] + "..."
                                bbox_truncado = draw.textbbox((0, 0), truncado, font=fuente)
                                if bbox_truncado[2] <= max_width:
                                    opcion = truncado
                                    break
                        draw.text((5, y), opcion, font=fuente, fill="white")

                    y += 20

                self.display_image(imagen)
                last_index = seleccion_index
                last_render_time = ahora

            if not scroll_needed or scroll_done:
                break

            await asyncio.sleep(scroll_delay)

    def limpiar_lcd(self):
        self.set_window()
        data = b'\x00\x00' * (240 * 240)
        for i in range(0, len(data), 4096):
            self.write_data(data[i:i + 4096])

