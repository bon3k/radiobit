import os
import time
import asyncio
import signal
import RPi.GPIO as GPIO
from modules.playback import ControlReproduccion
from modules.interface import InterfazLCD

# configuracion de pines
KEY1_PIN = 21
KEY2_PIN = 20
KEY3_PIN = 16
JOYSTICK_UP_PIN = 19
JOYSTICK_DOWN_PIN = 6
JOYSTICK_LEFT_PIN = 5
JOYSTICK_RIGHT_PIN = 26
JOYSTICK_PRESS_PIN = 13

# rutas
streams_file_path = "/home/radiobit/stream/data/streams.txt"
images_directory = "/home/radiobit/stream/data/stream-images/"
mp3_directory = "/home/radiobit/stream/data/main-mix/"

# inicializar modulos
interfaz_lcd = InterfazLCD()
control_reproduccion = ControlReproduccion(streams_file_path, images_directory, mp3_directory, interfaz_lcd)

# otros
debounce_time = 0.3
long_press_time = 0.3
fast_forward_active = False

in_menu = False  # <--- flag para controlar el joystick dentro del menu de pistas

def setup_gpio():
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    for pin in [KEY1_PIN, KEY2_PIN, KEY3_PIN,
                JOYSTICK_UP_PIN, JOYSTICK_DOWN_PIN,
                JOYSTICK_LEFT_PIN, JOYSTICK_RIGHT_PIN,
                JOYSTICK_PRESS_PIN]:
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

async def handle_joystick_action(pin, action_short, action_long):
    global fast_forward_active
    press_time = asyncio.get_event_loop().time()

    while not GPIO.input(pin):
        if asyncio.get_event_loop().time() - press_time >= long_press_time:
            fast_forward_active = True
            await action_long()
            return
        await asyncio.sleep(0.05)

    if not fast_forward_active:
        await action_short()
    fast_forward_active = False

async def leer_entrada_menu():
    """
    Espera una entrada de joystick: 'arriba', 'abajo' o 'enter'.
    Se usa exclusivamente durante la selección de pista.
    """
    timeout = 10  # segundos
    tiempo_inicio = asyncio.get_event_loop().time()
    while True:
        ahora = asyncio.get_event_loop().time()
        if not GPIO.input(JOYSTICK_RIGHT_PIN):
            interfaz_lcd.update_activity()
            await asyncio.sleep(0.2)
            return "arriba"
        if not GPIO.input(JOYSTICK_LEFT_PIN):
            interfaz_lcd.update_activity()
            await asyncio.sleep(0.2)
            return "abajo"
        if not GPIO.input(JOYSTICK_PRESS_PIN):
            interfaz_lcd.update_activity()
            await asyncio.sleep(0.2)
            return "enter"
        if not GPIO.input(JOYSTICK_UP_PIN):
            interfaz_lcd.update_activity()
            await asyncio.sleep(0.2)
            return "extra"
        if not GPIO.input(JOYSTICK_DOWN_PIN):
            interfaz_lcd.update_activity()
            await asyncio.sleep(0.2)
            return "volver"
        if ahora - tiempo_inicio > timeout:
            return None  # Inactividad

        await asyncio.sleep(0.05)

async def main_loop():
    global in_menu
    await control_reproduccion.iniciar()

    button3_press_time = None
    long_press_duration = 2

    while True:
        current_time = asyncio.get_event_loop().time()

        if not GPIO.input(KEY1_PIN):
            if not interfaz_lcd.backlight_on:
                interfaz_lcd.update_activity()
                await asyncio.sleep(debounce_time)
            else:
                interfaz_lcd.update_activity()
                await asyncio.sleep(debounce_time)
                await control_reproduccion.toggle_mode()

        if not GPIO.input(KEY2_PIN):
            if not interfaz_lcd.backlight_on:
                interfaz_lcd.update_activity()
                await asyncio.sleep(debounce_time)
            else:
                interfaz_lcd.update_activity()
                await asyncio.sleep(debounce_time)
                if control_reproduccion.mode == "mp3":
                    in_menu = True
                    await control_reproduccion.seleccionar_playlist(leer_entrada_menu)
                    in_menu = False


        if not GPIO.input(KEY3_PIN):
            if not interfaz_lcd.backlight_on:
                interfaz_lcd.update_activity()  # enciende retroiluminación
                await asyncio.sleep(debounce_time)
            else:
                interfaz_lcd.update_activity()
                if button3_press_time is None:
                    button3_press_time = current_time
                else:
                    press_duration = current_time - button3_press_time
                    if press_duration >= long_press_duration:
                        await control_reproduccion.menu_system(leer_entrada_menu)


        else:
            if button3_press_time is not None:
                press_duration = current_time - button3_press_time
                if press_duration < long_press_duration:
                    if control_reproduccion.mode == "mp3":
                        in_menu = True
                        playlist_index = control_reproduccion.current_playlist
                        playlist_tracks = control_reproduccion.playback_queue
                        await control_reproduccion.seleccionar_pista(leer_entrada_menu, playlist_index, playlist_tracks)
                        in_menu = False
                button3_press_time = None

        if not in_menu and not GPIO.input(JOYSTICK_PRESS_PIN):
            interfaz_lcd.update_activity()
            await asyncio.sleep(debounce_time)
            await control_reproduccion.toggle_pause()

        if not in_menu and not GPIO.input(JOYSTICK_UP_PIN):
            interfaz_lcd.update_activity()
            await handle_joystick_action(
                JOYSTICK_UP_PIN,
                lambda: control_reproduccion.change_mp3("up") if control_reproduccion.mode == "mp3"
                    else control_reproduccion.change_stream("up"),
                lambda: control_reproduccion.seek(10)
            )

        if not in_menu and not GPIO.input(JOYSTICK_DOWN_PIN):
            interfaz_lcd.update_activity()
            await handle_joystick_action(
                JOYSTICK_DOWN_PIN,
                lambda: control_reproduccion.change_mp3("down") if control_reproduccion.mode == "mp3"
                    else control_reproduccion.change_stream("down"),
                lambda: control_reproduccion.seek(-10)
            )

        if not in_menu and not GPIO.input(JOYSTICK_LEFT_PIN):
            interfaz_lcd.update_activity()
            await asyncio.sleep(debounce_time)
            await control_reproduccion.change_volume("down")

        if not in_menu and not GPIO.input(JOYSTICK_RIGHT_PIN):
            interfaz_lcd.update_activity()
            await asyncio.sleep(debounce_time)
            await control_reproduccion.change_volume("up")

        await asyncio.sleep(0.05)

async def main():
    setup_gpio()

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    # iniciar monitorizacion de inactividad
    interfaz_lcd.start_inactivity_monitor()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    task = asyncio.create_task(main_loop())

    await stop_event.wait()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    finally:
        await control_reproduccion.close()
        GPIO.cleanup()

if __name__ == "__main__":
    asyncio.run(main())

