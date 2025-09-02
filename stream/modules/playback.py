import os
import glob
import asyncio
from mpv import MPV
from urllib.parse import unquote
from modules.nostrbit import resolve_m3u8_async
from modules.snake_game import run_snake
import re
import time
import json
from pathlib import Path

CONFIG_FILE = Path("/home/radiobit/config.json")

def cargar_config():
    # lee config.json, si esta vacio o corrupto lo crea con valores por defecto
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass

    config = {
        "video_enabled": False,
        "replaygain_mode": "track"
    }
    guardar_config(config)
    return config

def guardar_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f)

class ControlReproduccion:
    def __init__(self, streams_file_path, images_directory, mp3_directory, lcd_interface):
        self.lcd_interface = lcd_interface
        self.streams = self.load_streams(streams_file_path)
        self.images = self.load_images(images_directory)
        self.mp3_directory = mp3_directory
        self.playlists = self.load_playlists(mp3_directory)
        self.current_playlist = 0
        self.current_mp3_index = 0
        self.current_stream = 0
        self.mode = "mp3"  # # arranca en modo mp3
        self.is_paused = False
        self.estado_reproduccion = {"time": 0, "duration": 0}
        self.update_task = None
        self.ultimo_titulo = None  # # evita redibujar pantalla si el titulo no ha cambiado
        self.en_menu = False  # # flag para los controles de menu
        self.last_change_time = 0  # # evita dobles cambios de stream por multiples pulsaciones rapidas
        self.last_down_press_time = 0  # # controla el tiempo transcurrido despues de pulsar el boton de retroceder pista
        self.repetir_playlist = True  # # repetir playlist al terminar la cola de reproduccion
        self.playback_queue = []
        self.loop = None
        self.manual_change = False    # flag para saltar on_end_file durante cambio manual
        self.menu_task = None  # # flag para activar bucle async dentro del menu (scroll horizontal)
        config = cargar_config()
        self.video_enabled = config.get("video_enabled", False)  # video desactivado por defecto
        self.replaygain_mode = config.get("replaygain_mode", "track")
        self._create_mpv()  # crear el objeto mpv segun config.json

    def _create_mpv(self):
        """(Re)crea self.mpv_player según self.video_enabled y registra observers/callbacks."""
        common_kwargs = dict(
            ytdl=True,
            loop_playlist="no",
            volume=40,
            replaygain='album',
            replaygain_preamp=0,
            replaygain_clip='no'
        )

        # termina player anterior si existe
        try:
            if hasattr(self, "mpv_player") and self.mpv_player is not None:
                try:
                    self.mpv_player.terminate()
                except Exception:
                    # ignoramos errores al terminar
                    pass
        except Exception:
            pass

        # Crear nuevo mpv: si video_enabled -> no pasa 'video'
        if self.video_enabled:
            self.mpv_player = MPV(**common_kwargs)
        else:
            self.mpv_player = MPV(video='no', **common_kwargs)

        self.mpv_player.observe_property('time-pos', self.actualizar_estado)
        self.mpv_player.observe_property('duration', self.actualizar_estado)
        self.mpv_player.observe_property('volume', self.actualizar_estado)

        @self.mpv_player.event_callback('end-file')

        # gestiona el evento mpv de fin de pista para handle_end_file
        def on_end_file(event):
            if self.manual_change:
                return

            reason_code = getattr(event.data, 'reason', None)

            # convierte bytes a string
            if isinstance(reason_code, bytes):
                reason_str = reason_code.decode()
            elif isinstance(reason_code, int):
                # mapear codigo a texto
                reason_map = {0: 'eof', 1: 'stop', 2: 'error', 3: 'quit'}
                reason_str = reason_map.get(reason_code, str(reason_code))
            else:
                reason_str = str(reason_code)

            # solo avanzar si finalizo naturalmente
            if self.mode == "mp3" and not self.is_paused and reason_str == 'eof':
                if self.loop and self.loop.is_running():
                    asyncio.run_coroutine_threadsafe(self.handle_end_file(), self.loop)

        self.NPUB_RE = re.compile(r"^npub1[ac-hj-np-z02-9]{58}$")

    def _es_npub(self, texto: str) -> bool:
        return bool(self.NPUB_RE.match(texto))

    async def resolve_all_npubs(self, entries):
        resolved = []
        for entry in entries:
            if self._es_npub(entry):
                try:
                    url = await resolve_m3u8_async(entry)
                    resolved.append(url if url else "")
                except Exception:
                    resolved.append("")
            else:
                resolved.append(entry)
        return resolved

    def load_streams(self, file_path):
        if os.path.exists(file_path):
            with open(file_path, "r") as f:
                return [line.strip() for line in f if line.strip()]
        return []

    def load_images(self, directory):
        images = {}
        for img_file in os.listdir(directory):
            if img_file.endswith((".png", ".jpg", ".jpeg")):
                try:
                    index = int(os.path.splitext(img_file)[0].split("_")[0])
                    images[index] = os.path.join(directory, img_file)
                except ValueError:
                    continue
        return images

    def load_playlists(self, mp3_directory):
        playlists = []
        formatos_validos = (".mp3", ".flac", ".ogg", ".wav", ".aac", ".m4a", ".aiff", ".aif")
        for root, dirs, files in sorted(os.walk(mp3_directory), key=lambda x: x[0]):
            archivos_m3u = [f for f in files if f.endswith('.m3u')]
            if archivos_m3u:
                for m3u in archivos_m3u:
                    m3u_path = os.path.join(root, m3u)
                    mp3_files = self.load_m3u_playlist(m3u_path)
                    if mp3_files:
                        playlists.append((m3u_path, mp3_files))
            else:
                pistas = [os.path.join(root, f) for f in sorted(files) if f.lower().endswith(formatos_validos)]
                if pistas:
                    playlists.append((os.path.join(root, ''), pistas))
        return playlists

    def load_m3u_playlist(self, m3u_file_path):
        mp3_files = []
        with open(m3u_file_path, 'r') as m3u_file:
            for line in m3u_file:
                line = line.strip()
                if line and not line.startswith('#'):
                    path = os.path.join(os.path.dirname(m3u_file_path), line) if not os.path.isabs(line) else line
                    mp3_files.append(unquote(path))
        return mp3_files

    # arranca el sistema: resuelve npub, prepara la playlist, empieza a reproducir y lanza update_loop
    async def iniciar(self):
        self.loop = asyncio.get_running_loop()
        self.streams = await self.resolve_all_npubs(self.streams)
        if self.playlists:
            self.current_playlist = 0
            self.current_mp3_index = 0
            self.playback_queue = self.playlists[self.current_playlist][1]
            await self.play_current_mp3()
        self.update_task = asyncio.create_task(self.update_loop())

    # obtiene de mpv la posicion de reproduccion y duracion de pista
    def actualizar_estado(self, name, value):
        if name == "time-pos":
            self.estado_reproduccion["time"] = int(value) if value else 0
        elif name == "duration":
            self.estado_reproduccion["duration"] = int(value) if value else 0
        elif name == "volume":
            self.estado_reproduccion["volume"] = int(value) if value else 0

    # maneja el cambio de pista cuando llama on_end_file
    async def handle_end_file(self):
        if not self.playback_queue:
            return
        self.current_mp3_index += 1
        if self.current_mp3_index >= len(self.playback_queue):
            if self.repetir_playlist:
                self.current_mp3_index = 0
            else:
                self.current_mp3_index = len(self.playback_queue) - 1
                await asyncio.to_thread(self.mpv_player.stop)
                return
        await asyncio.to_thread(self.mpv_player.play, self.playback_queue[self.current_mp3_index])

    # refresca la pantalla con el estado actual de reproduccion (pista, tiempo, batería)
    async def update_loop(self):
        last_battery_update = 0
        while True:
            await asyncio.sleep(0.1)
            if self.en_menu:
                continue
            if self.mode == "mp3":
                actual = self.mp3_actual()
                if actual:
                    titulo_actual = os.path.basename(actual)
                    if titulo_actual != self.ultimo_titulo:
                        self.ultimo_titulo = titulo_actual
                    self.lcd_interface.display_mp3_info(
                        self.ultimo_titulo,
                        self.estado_reproduccion["time"],
                        self.estado_reproduccion["duration"],
                        volume_level=int(self.estado_reproduccion["volume"])
                    )
            elif self.mode == "stream":
                now = time.time()
                if now - last_battery_update > 10:
                    last_battery_update = now
                    self.lcd_interface.update_battery_icon_only()

    # detiene mpv (manejo interno)
    async def stop_playback(self):
        await asyncio.to_thread(self.mpv_player.stop)

    # reproduce stream actual
    async def start_stream(self, stream_index: int, direction="forward"):
        if not (0 <= stream_index < len(self.streams)):
            return
        stream_url = self.streams[stream_index]
        if not stream_url:
            next_index = (stream_index + 1) % len(self.streams) if direction == "forward" else (stream_index - 1) % len(self.streams)
            self.current_stream = next_index
            await self.start_stream(self.current_stream, direction=direction)
            return

        self.is_paused = False
        await self.stop_playback()
        try:
            await asyncio.to_thread(self.mpv_player.play, stream_url)
            img = self.images.get(stream_index, "/home/radiobit/stream/data/stream-images/default.png")
            self.ultimo_frame_stream = img  # guarda la imagen actual para restaurar al cerrar snake.py
            self.lcd_interface.display_image(img)
            self.lcd_interface.update_battery_icon_only()
        except Exception:
            next_index = (stream_index + 1) % len(self.streams) if direction == "forward" else (stream_index - 1) % len(self.streams)
            self.current_stream = next_index
            await self.start_stream(self.current_stream, direction=direction)

    # funcion auxiliar. actuliza indices para play_current_mp3 y change_mp3
    def mp3_actual(self):
        try:
            return self.playback_queue[self.current_mp3_index]
        except (IndexError, TypeError):
            return None

    # reproduce mp3 actual
    async def play_current_mp3(self):
        if not self.playback_queue:
            return
        mp3_file = self.mp3_actual()
        if mp3_file:
            try:
                await self.stop_playback()
                await asyncio.to_thread(self.mpv_player.play, mp3_file)
            except Exception as e:
                print(f"Error al reproducir mp3: {e}")

    # cambio manual stream
    async def change_stream(self, direction):
        now = time.time()
        if now - self.last_change_time < 1.0:
            return

        self.manual_change = True

        await self.stop_playback()

        self.last_change_time = now
        if self.mode == "stream":
            if direction == "up":
                self.current_stream = (self.current_stream + 1) % len(self.streams)
                await self.start_stream(self.current_stream, direction="forward")
            elif direction == "down":
                self.current_stream = (self.current_stream - 1) % len(self.streams)
                await self.start_stream(self.current_stream, direction="backward")

            self.manual_change = False

    # cambio manual mp3
    async def change_mp3(self, direction):
        if self.mode != "mp3" or not self.playback_queue:
            return

        self.manual_change = True

        await self.stop_playback()

        if direction == "up":
            self.current_mp3_index = (self.current_mp3_index + 1) % len(self.playback_queue)
            await self.play_current_mp3()
        elif direction == "down":
            now = time.time()
            tiempo_actual = self.estado_reproduccion["time"]
            if now - self.last_down_press_time < 2 or tiempo_actual < 3:
                self.current_mp3_index = (self.current_mp3_index - 1) % len(self.playback_queue)
            self.last_down_press_time = now
            await self.play_current_mp3()

        self.manual_change = False

    # cambio de modo stream/mp3
    async def toggle_mode(self):

        await self.stop_playback()

        if self.mode == "mp3":
            self.mode = "stream"
            await self.start_stream(self.current_stream)
        else:
            self.mode = "mp3"
            await self.play_current_mp3()

    # pausa mpv
    async def toggle_pause(self):
        await asyncio.to_thread(setattr, self.mpv_player, 'pause', not self.mpv_player.pause)
        self.is_paused = self.mpv_player.pause

    # NO SE ESTA USANDO. sirve para cambiar de playlist sin abrir el menu
    async def change_playlist(self):
        self.playlists = self.load_playlists(self.mp3_directory)
        if self.mode == "mp3" and self.playlists:
            self.current_playlist = (self.current_playlist + 1) % len(self.playlists)
            self.current_mp3_index = 0
            self.playback_queue = self.playlists[self.current_playlist][1]
            await self.play_current_mp3()

    # volumen
    async def change_volume(self, direction):
        if direction == "up":
            self.mpv_player.volume = min(self.mpv_player.volume + 3, 120)
        elif direction == "down":
            self.mpv_player.volume = max(self.mpv_player.volume - 3, 0)

    # retroceso/avance rapido
    async def seek(self, seconds):
        if self.mode == "mp3" and self.estado_reproduccion["duration"] > 0:
            new_time = max(0, min(self.estado_reproduccion["time"] + seconds, self.estado_reproduccion["duration"]))
            await asyncio.to_thread(self.mpv_player.seek, new_time, "absolute")
            self.estado_reproduccion["time"] = new_time
    # reinicia mpv (video ON/OFF)
    def reboot_player(self):
        """Recrea mpv en el proceso actual y reanuda la reproduccion"""
        # actualizar/crear mpv con la opcion actual
        self._create_mpv()

        # reanudar reproduccion
        try:
            if self.loop and self.loop.is_running():
                if self.mode == "stream":
                    asyncio.run_coroutine_threadsafe(self.start_stream(self.current_stream), self.loop)
                else:
                    asyncio.run_coroutine_threadsafe(self.play_current_mp3(), self.loop)
        except Exception:
            pass

    async def toggle_replaygain_mode(self):
        self.replaygain_mode = "album" if self.replaygain_mode == "track" else "track"

        # Guardar en config.json
        config = cargar_config()
        config["replaygain_mode"] = self.replaygain_mode
        guardar_config(config)

        # Aplicar el cambio en mpv
        try:
            self.mpv_player.replaygain = self.replaygain_mode
        except Exception:
            pass
        
    def refresh_display(self):
        """Refresca la pantalla según el modo actual."""
        if self.mode == "stream" and hasattr(self, "ultimo_frame_stream"):
            self.lcd_interface.display_image(self.ultimo_frame_stream)
        elif self.mode == "mp3":
            mp3_file = self.mp3_actual()
            if mp3_file:
                titulo = os.path.basename(mp3_file)
                self.lcd_interface.display_mp3_info(
                    titulo,
                    self.estado_reproduccion.get("time", 0),
                    self.estado_reproduccion.get("duration", 0),
                    volume_level=int(self.estado_reproduccion.get("volume", 0))
                )

    # menu pistas
    async def seleccionar_pista(self, leer_entrada, playlist_index, playlist_tracks):
        playlist = playlist_tracks
        total = len(playlist)
        # Si abre la misma playlist que la actual, empieza en current_mp3_index
        # Si es otra playlist, empieza en 0
        if playlist_index == self.current_playlist:
            indice = self.current_mp3_index
        else:
            indice = 0
        ventana_size = 10
        offset = 0

        self.en_menu = True

        while True:
            if indice < offset:
                offset = indice
            elif indice >= offset + ventana_size:
                offset = indice - ventana_size + 1

            lineas = []
            for i in range(offset, min(offset + ventana_size, total)):
                nombre = os.path.basename(playlist[i]).replace("_", " ").replace(".mp3", "")
                prefijo = "> " if i == indice else "  "
                reproduciendo = "* " if (self.current_playlist == playlist_index and i == self.current_mp3_index) else ""

                lineas.append(prefijo + reproduciendo + nombre)

            await self.mostrar_menu_async(lineas, indice - offset, titulo=f"TRACK {indice + 1}/{total}")

            entrada = await leer_entrada()

            if entrada == "abajo":
                indice = (indice + 1) % total
            elif entrada == "arriba":
                indice = (indice - 1) % total
            elif entrada == "enter":
                if self.current_playlist != playlist_index:
                    # cambiar a la nueva playlist
                    self.current_playlist = playlist_index
                    self.playback_queue = playlist_tracks
                    self.current_mp3_index = indice
                    await self.play_current_mp3()
                elif self.current_mp3_index != indice:
                    # cambiar solo la pista dentro de la misma playlist
                    self.current_mp3_index = indice
                    await self.play_current_mp3()
                break
            elif entrada == "volver":
                return await self.seleccionar_playlist(leer_entrada)
            elif entrada is None:
                break

        self.en_menu = False
        await self.cerrar_menu_async()

    # menu playlist
    async def seleccionar_playlist(self, leer_entrada):
        if not self.playlists:
            return

        self.en_menu = True

        seleccion = self.current_playlist
        total = len(self.playlists)

        # cursor_index para controlar dónde esta el cursor en el menú
        cursor_index = 0  # siempre empieza arriba en un menu nuevo
        ventana_size = 10
        offset = 0

        while True:
            if cursor_index < offset:
                offset = cursor_index
            elif cursor_index >= offset + ventana_size:
                offset = cursor_index - ventana_size + 1

            lineas = []
            for i in range(offset, min(offset + ventana_size, total)):
                nombre = os.path.basename(os.path.dirname(self.playlists[i][0]))
                prefijo = "> " if i == cursor_index else "  "
                reproduciendo = "* " if i == self.current_playlist else ""
                lineas.append(prefijo + reproduciendo + nombre)

            await self.mostrar_menu_async(lineas, cursor_index - offset, titulo=f"PLAYLIST {cursor_index + 1}/{total}")


            entrada = await leer_entrada()

            if entrada == "arriba":
                cursor_index = (cursor_index - 1) % total
            elif entrada == "abajo":
                cursor_index = (cursor_index + 1) % total
            elif entrada == "enter":
                if self.current_playlist != cursor_index:
                    self.current_playlist = cursor_index
                    self.current_mp3_index = 0
                    self.playback_queue = self.playlists[self.current_playlist][1]
                    await self.play_current_mp3()
                break
            elif entrada == "extra":
                # Abrir menu de pistas de la playlist bajo el cursor
                playlist_index = cursor_index
                playlist_tracks = self.playlists[playlist_index][1]  # lista de pistas de esa playlist

                # Guarda el indice actual para restaurar despues si no se selecciona nada
                old_index = self.current_mp3_index

                # Determinar índice inicial del cursor
                if playlist_index == self.current_playlist:
                    start_index = self.current_mp3_index
                else:
                    start_index = 0

                self.current_mp3_index = start_index
                await self.seleccionar_pista(leer_entrada, playlist_index, playlist_tracks)

                # restaurar indice si no se selecciono otra pista
                if self.current_mp3_index == start_index:
                    self.current_mp3_index = old_index
                break
            elif entrada is None:
                break

        self.en_menu = False
        await self.cerrar_menu_async()


    # menu system
    async def menu_system(self, leer_entrada):
        opciones = [
            "Resume Playback",
            "Repeat playlist: ON" if self.repetir_playlist else "Repeat playlist: OFF",
            "Video",
            "ReplayGain: " + self.replaygain_mode.upper(),
            "Refresh nostrbit",
            "Refresh playlists",
            "Play snake",
            "Reboot",
            "Shutdown"
        ]
        seleccion = 0
        total = len(opciones)

        self.en_menu = True

        while True:
            # actualiza el texto segun el estado actual
            opciones[1] = "Repeat playlist: ON" if self.repetir_playlist else "Repeat playlist: OFF"
            opciones[2] = "Video: ON" if self.video_enabled else "Video: OFF"
            opciones[3] = "ReplayGain: " + self.replaygain_mode.upper()

            await self.mostrar_menu_async(opciones, seleccion, titulo="SYSTEM")

            entrada = await leer_entrada()

            if entrada == "abajo":
                seleccion = (seleccion + 1) % total
            elif entrada == "arriba":
                seleccion = (seleccion - 1) % total
            elif entrada == "enter":
                if seleccion == 0:
                    self.refresh_display()
                    break
                elif seleccion == 1:
                    self.repetir_playlist = not self.repetir_playlist
                    self.refresh_display()
                    break
                elif seleccion == 2:
                    # alterna la opcion manteniendo otras claves del config
                    config = cargar_config()
                    config['video_enabled'] = not config.get('video_enabled', False)
                    guardar_config(config)
                    self.video_enabled = config['video_enabled']
                    # recrear mpv con la nueva configuracion
                    self.reboot_player()
                    break
                elif seleccion == 3:
                    # alterna ReplayGain track/album
                    await self.toggle_replaygain_mode()
                    self.refresh_display()
                    break
                elif seleccion == 4:
                    await self.cerrar_menu_async()
                    img = self.lcd_interface.draw_text_on_lcd("Resolving links...")
                    self.lcd_interface.display_image(img)
                    nuevos_streams = await self.resolve_all_npubs(self.load_streams("/home/radiobit/stream/data/streams.txt"))
                    self.streams = nuevos_streams
                    img = self.lcd_interface.draw_text_on_lcd("Links resolved")
                    self.lcd_interface.display_image(img)
                    await asyncio.sleep(1.5)
                    self.refresh_display()
                    break
                elif seleccion == 5:
                    await self.cerrar_menu_async()

                    # guarda ruta de la playlist actual y la pista actual
                    ruta_actual = self.playlists[self.current_playlist][0] if self.playlists else None
                    pista_actual = self.mp3_actual()

                    # recarga playlists
                    self.playlists = self.load_playlists(self.mp3_directory)

                    nuevo_indice_playlist = 0
                    nuevo_indice_pista = 0

                    if ruta_actual:
                        for i, (ruta, pistas) in enumerate(self.playlists):
                            if ruta == ruta_actual:
                                nuevo_indice_playlist = i
                                if pista_actual:
                                    try:
                                        nuevo_indice_pista = pistas.index(pista_actual)
                                    except ValueError:
                                        nuevo_indice_pista = 0
                                break

                    self.current_playlist = nuevo_indice_playlist
                    self.playback_queue = self.playlists[self.current_playlist][1] if self.playlists else []
                    self.current_mp3_index = nuevo_indice_pista if self.playback_queue else 0

                    img = self.lcd_interface.draw_text_on_lcd("Playlists updated")
                    self.lcd_interface.display_image(img)
                    await asyncio.sleep(1.5)
                    self.refresh_display()
                    break

                elif seleccion == 6:
                    from modules.snake_game import run_snake
                    await self.cerrar_menu_async()
                    await run_snake(self.lcd_interface)
                    # restaurar imagen del stream si estaba activo
                    self.refresh_display()
                    break
                elif seleccion == 7:
                    await self.cerrar_menu_async()
                    img = self.lcd_interface.draw_text_on_lcd("Rebooting...")
                    self.lcd_interface.display_image(img)
                    await self.close()  # asegura cerrar streams
                    os.system("sync")
                    await asyncio.sleep(0.8)
                    os.system("sudo reboot")
                    break
                elif seleccion == 8:
                    await self.cerrar_menu_async()
                    img = self.lcd_interface.draw_text_on_lcd("Power down...")
                    self.lcd_interface.display_image(img)
                    await self.close()  # asegura cerrar streams
                    os.system("sync")
                    await asyncio.sleep(0.8)
                    os.system("sudo systemctl poweroff")
                    break

            elif entrada is None:
                self.refresh_display()
                break

        self.en_menu = False
        await self.cerrar_menu_async()

    # bucle asincrono dentro del menu (scroll texto)
    async def mostrar_menu_async(self, opciones, seleccion_index, titulo=None):
        # cancela tarea previa si existe
        if self.menu_task:
            self.menu_task.cancel()
            try:
                await self.menu_task
            except asyncio.CancelledError:
                pass
            self.menu_task = None

        # crear nueva tarea para mostrar menu
        self.menu_task = asyncio.create_task(
            self.lcd_interface.display_menu(opciones, seleccion_index, titulo=titulo)
        )

    # cierra el bucle al salir del menu
    async def cerrar_menu_async(self):
        if self.menu_task:
            self.menu_task.cancel()
            try:
                await self.menu_task
            except asyncio.CancelledError:
                pass
            self.menu_task = None

    # detiene tareas y cierra mpv
    async def close(self):
        if self.update_task:
            self.update_task.cancel()
            try:
                await self.update_task
            except asyncio.CancelledError:
                pass
        await asyncio.to_thread(self.mpv_player.terminate)

