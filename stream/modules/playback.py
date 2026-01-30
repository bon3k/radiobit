import os
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
        f.write("\n")


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
        self.mode = "idle"
        self.estado_reproduccion = {"time": 0, "duration": 0}
        self.update_task = None
        self.ultimo_titulo = None  # # evita redibujar pantalla si el titulo no ha cambiado
        self.en_menu = False  # # flag para los controles de menu
        self.last_change_time = 0  # # evita dobles cambios de stream por multiples pulsaciones rapidas
        self.repetir_playlist = True  # # repetir playlist al terminar la cola de reproduccion
        self.playback_queue = []
        self.loop = None
        self.manual_change = False    # flag para saltar on_end_file durante cambio manual
        self.menu_task = None  # # flag para activar bucle async dentro del menu (scroll horizontal)
        config = cargar_config()
        self.video_enabled = config.get("video_enabled", False)  # video desactivado por defecto
        self.replaygain_mode = config.get("replaygain_mode", "track")
        self._create_mpv()  # crear el objeto mpv segun config.json


            ###### --------------- LOAD MPV --------------- ######

    def _create_mpv(self):
        """(Re)crea self.mpv_player según self.video_enabled y registra observers/callbacks."""
        common_kwargs = dict(
            ytdl=True,
            loop_playlist="no",
            volume=40,
            replaygain=self.replaygain_mode,
            replaygain_preamp=0,
            replaygain_clip='no'
        )

        # termina player anterior si existe
        try:
            if hasattr(self, "mpv_player") and self.mpv_player is not None:
                try:
                    self.mpv_player.terminate()
                except Exception:
                    # ignora errores al terminar
                    pass
        except Exception:
            pass

        # Crear nuevo objeto mpv
        if self.video_enabled:
            self.mpv_player = MPV(**common_kwargs)
        else:
            self.mpv_player = MPV(video='no', **common_kwargs)

        self.mpv_player.observe_property('time-pos', self.actualizar_estado)
        self.mpv_player.observe_property('duration', self.actualizar_estado)
        self.mpv_player.observe_property('volume', self.actualizar_estado)

        @self.mpv_player.event_callback('end-file')

        # gestiona el evento mpv de fin de pista
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

            # solo avanzar si termina naturalmente
            if self.mode == "mp3" and reason_str == 'eof':
                if self.loop and self.loop.is_running():
                    asyncio.run_coroutine_threadsafe(self.transition("NEXT_MP3"), self.loop)

        self.NIP19_RE = re.compile(r"^(npub1|nprofile1)[ac-hj-np-z02-9]+$")

    def _es_nip19(self, texto: str) -> bool:
        return bool(self.NIP19_RE.match(texto))


            ###### --------------- LOAD DATA --------------- ######

    async def resolve_all_npubs(self, entries):
        resolved = []
        for entry in entries:
            entry = entry.strip()
            if self._es_nip19(entry):
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


            ###### --------------- INIT SYSTEM --------------- ######

    # arranca el sistema: resuelve npub, arranca en idle y lanza update_loop
    async def iniciar(self):
        self.loop = asyncio.get_running_loop()
        self.streams = await self.resolve_all_npubs(self.streams)
        await self.enter_idle()
        self.update_task = asyncio.create_task(self.update_loop())


    # obtiene de mpv la posicion de reproduccion y duracion de pista
    def actualizar_estado(self, name, value):
        if name == "time-pos":
            self.estado_reproduccion["time"] = int(value) if value else 0
        elif name == "duration":
            self.estado_reproduccion["duration"] = int(value) if value else 0
        elif name == "volume":
            self.estado_reproduccion["volume"] = int(value) if value else 0


    # handle playlist/queue
    async def play_playlist(self, playlist_index, track_index=0):
        if not (0 <= playlist_index < len(self.playlists)):
            return

        await self.stop_playback()

        self.current_playlist = playlist_index
        self.playback_queue = self.playlists[playlist_index][1]
        self.current_mp3_index = track_index
        self.mode = "mp3"

        await self.play_current_mp3()


    #### ---- playback state controller ---- ####
    async def transition(self, action, payload=None):
        """
        Metodo central de transicion para:
        - reproducir pistas o streams
        - avanzar/retroceder pistas
        - reiniciar pistas
        """
        self.manual_change = True
        try:

            if action == "PLAY_MP3":
                # comprobar si la pista real es la misma que esta sonando
                pista_actual = self.mp3_actual()

                pista_solicitada = (
                    self.playback_queue[payload]
                    if (
                        self.playback_queue
                        and payload is not None
                        and 0 <= payload < len(self.playback_queue)
                    )
                    else None
                )
                # si esta sonando exactamente esa pista, no hacer nada
                if (
                    self.mode == "mp3"
                    and pista_actual is not None
                    and pista_actual == pista_solicitada
                ):
                    return
                self.ultimo_frame_stream = None
                await self.stop_playback()
                self.mode = "mp3"
                self.current_mp3_index = payload
                await self.play_current_mp3()


            elif action == "NEXT_MP3":
                if not self.playback_queue:
                    self.manual_change = False
                    return
                
                await self.stop_playback()
                self.current_mp3_index += 1
                if self.current_mp3_index >= len(self.playback_queue):
                    if self.repetir_playlist:
                        self.current_mp3_index = 0
                    else:
                        await self.enter_idle()
                        return
                    
                await self.play_current_mp3()


            elif action == "PREV_MP3":
                if not self.playback_queue:
                    self.manual_change = False
                    return
                
                tiempo_actual = self.estado_reproduccion.get("time", 0)
                if tiempo_actual > 3:
                    # reinicia la pista actual
                    await self.stop_playback()
                    await self.play_current_mp3()
                else:
                    # retrocede a la pista anterior
                    self.current_mp3_index = (self.current_mp3_index - 1) % len(self.playback_queue)
                    await self.play_current_mp3()


            elif action == "PLAY_STREAM":
                if not self.streams:
                    return
                
                if payload is not None:
                    self.current_stream = payload
                await self.start_stream(self.current_stream)

        finally:
            self.manual_change = False


    # refresh pantalla con el estado actual de reproduccion (pista, tiempo, bateria)
    async def update_loop(self):
        last_battery_update = 0

        last_title = None
        last_time = None
        last_duration = None
        last_volume = None
        last_mode = None

        while True:
            await asyncio.sleep(0.2)

            if self.en_menu:
                continue

            # Detectar cambio de modo
            if self.mode != last_mode:
                last_mode = self.mode
                last_title = None
                last_time = None
                last_duration = None
                last_volume = None

            if self.mode == "mp3":
                actual = self.mp3_actual()
                if not actual:
                    continue

                titulo_actual = os.path.basename(actual)
                tiempo = self.estado_reproduccion.get("time", 0)
                duracion = self.estado_reproduccion.get("duration", 0)
                volumen = int(self.estado_reproduccion.get("volume", 0))

                # Redibujar solo si algo cambió
                if (
                    titulo_actual != last_title
                    or tiempo != last_time
                    or duracion != last_duration
                    or volumen != last_volume
                ):
                    last_title = titulo_actual
                    last_time = tiempo
                    last_duration = duracion
                    last_volume = volumen

                    await asyncio.to_thread(
                        self.lcd_interface.display_mp3_info,
                        titulo_actual,
                        tiempo,
                        duracion,
                        volume_level=volumen
                    )


            elif self.mode == "stream":
                now = time.time()
                if now - last_battery_update > 10:
                    last_battery_update = now
                    await asyncio.to_thread(self.lcd_interface.update_battery_icon_only)

            elif self.mode == "idle":
                continue

    # detiene mpv
    async def stop_playback(self):
        await asyncio.to_thread(self.mpv_player.stop)


    # reproduce stream actual
    async def start_stream(self, stream_index: int):
        if not self.streams or not (0 <= stream_index < len(self.streams)):
            return
        stream_url = self.streams[stream_index].strip()
        await self.stop_playback()
        self.mode = "stream"
        self.current_stream = stream_index
        # stream vacio
        if not stream_url:
            await self.stop_playback()
            self.current_stream = stream_index  # marcar indice actual
            img = self.lcd_interface.draw_text_on_lcd(
                f"STREAM {stream_index + 1}/{len(self.streams)}\nOFFLINE"
            )
            self.ultimo_frame_stream = img
            self.lcd_interface.display_image(img)
            return
        
        try:
            await asyncio.to_thread(self.mpv_player.play, stream_url)
            self.mpv_player.pause = False
            img = self.images.get(
                stream_index,
                "/home/radiobit/stream/data/stream-images/default.png"
            )
            self.ultimo_frame_stream = img
            self.lcd_interface.display_image(img)
            self.lcd_interface.update_battery_icon_only()
        except Exception:
            img = self.lcd_interface.draw_text_on_lcd("ERROR\nPlay failed")
            self.lcd_interface.display_image(img)


    # funcion auxiliar. entrega pista actual
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
            self.ultimo_frame_stream = None
            try:
                await self.stop_playback()
                await asyncio.sleep(0.05)
                await asyncio.to_thread(self.mpv_player.play, mp3_file)
                self.mpv_player.pause = False
            except Exception as e:
                print(f"Error al reproducir mp3: {e}")


    # cambio manual stream
    async def change_stream(self, direction):
        now = time.time()
        if now - self.last_change_time < 1.0:
            return
        
        self.last_change_time = now

        if not self.streams:
            return

        if direction == "forward":
            next_index = (self.current_stream + 1) % len(self.streams)
        else:
            next_index = (self.current_stream - 1 + len(self.streams)) % len(self.streams)

        prev_stream = self.current_stream

        await self.transition("PLAY_STREAM", next_index)

        if self.current_stream != prev_stream:
            self.last_change_time = now


    # cambio manual mp3
    async def change_mp3(self, direction):
        if self.mode == "idle":
            if self.playlists:
                await self.play_playlist(self.current_playlist, self.current_mp3_index)
            return
        
        if self.mode != "mp3" or not self.playback_queue:
            return
        
        if direction == "up":
            await self.transition("NEXT_MP3")
        elif direction == "down":
            await self.transition("PREV_MP3")


    # cambio de modo stream/mp3
    async def toggle_mode(self):
        if self.mode == "idle":
            # prioridad: stream si existen, si no mp3
            if self.streams:
                await self.transition("PLAY_STREAM", self.current_stream)
            elif self.playlists:
                await self.play_playlist(self.current_playlist, self.current_mp3_index)
                
        elif self.mode == "mp3":
            await self.transition("PLAY_STREAM", self.current_stream)
            
        elif self.mode == "stream":
            if self.playlists:
                await self.play_playlist(self.current_playlist, self.current_mp3_index)   


    async def enter_idle(self):
        await self.stop_playback()
        self.mpv_player.pause = False
        self.mode = "idle"
        self.ultimo_titulo = None
        self.playback_queue = []
        self.current_mp3_index = 0

        # pantalla idle
        img = self.lcd_interface.draw_text_on_lcd(
            "(o_o)"
        )
        self.lcd_interface.display_image(img)


    # pausa mpv
    async def toggle_pause(self):
        self.mpv_player.pause = not self.mpv_player.pause


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


            ###### --------------- MENU SWITCHES --------------- ######

    # reinicia mpv (video ON/OFF)
    def reboot_player(self):
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

    # replaygain album/track
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
        if self.mode == "stream" and hasattr(self, "ultimo_frame_stream"):
            self.lcd_interface.display_image(self.ultimo_frame_stream)
            self.lcd_interface.update_battery_icon_only()
        elif self.mode == "mp3":
            mp3_file = self.mp3_actual()
            if mp3_file:
                titulo = os.path.basename(mp3_file)
                img = self.lcd_interface.create_mp3_snapshot(
                    titulo,
                    self.estado_reproduccion.get("time", 0),
                    self.estado_reproduccion.get("duration", 0),
                    volume_level=int(self.estado_reproduccion.get("volume", 0))
                )

                self.lcd_interface.display_image(img)
                self.ultimo_frame_mp3 = img
            return

        elif self.mode == "idle":
            img = getattr(self, "idle_image", None)
            if img is None:
                img = self.lcd_interface.draw_text_on_lcd("(o_o)")
                self.idle_image = img

            self.lcd_interface.display_image(img)
            return

            ###### --------------- ALL MENU --------------- ######

    # menu pistas
    async def seleccionar_pista(self, leer_entrada, playlist_index, playlist_tracks):
        playlist = playlist_tracks
        total = len(playlist)
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
                    await self.play_playlist(playlist_index, indice)
                else:
                    await self.transition("PLAY_MP3", indice)
                break
            elif entrada == "volver":
                return await self.seleccionar_playlist(leer_entrada)
            elif entrada is None:
                break

        self.en_menu = False
        await self.cerrar_menu_async()
        self.refresh_display()


    # menu playlist
    async def seleccionar_playlist(self, leer_entrada):
        if not self.playlists:
            return

        self.en_menu = True

        seleccion = self.current_playlist
        total = len(self.playlists)

        # cursor_index para controlar donde esta el cursor en el menu
        cursor_index = self.current_playlist
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
                    await self.play_playlist(cursor_index, 0)
                break
            elif entrada == "extra":
                # Abrir menu de pistas de la playlist bajo el cursor
                playlist_index = cursor_index
                playlist_tracks = self.playlists[playlist_index][1]  # lista de pistas de esa playlist

                # Abrir menu de pistas SIN tocar estado global
                await self.seleccionar_pista(
                    leer_entrada,
                    playlist_index,
                    playlist_tracks
                )

                break
            elif entrada is None:
                break

        self.en_menu = False
        await self.cerrar_menu_async()
        self.refresh_display()


    # menu system
    async def menu_system(self, leer_entrada):
        self.en_menu = True
        was_paused = self.mpv_player.pause
        self.frame_pause_snapshot = None

        if was_paused:
            if self.mode == "mp3":
                mp3_file = self.mp3_actual()
                if mp3_file:
                    titulo = os.path.basename(mp3_file)
                    self.frame_pause_snapshot = self.lcd_interface.create_mp3_snapshot(
                        titulo,
                        self.estado_reproduccion.get("time", 0),
                        self.estado_reproduccion.get("duration", 0),
                        volume_level=int(self.estado_reproduccion.get("volume", 0))
                    )
            elif self.mode == "stream":
                self.frame_pause_snapshot = self.ultimo_frame_stream

        opciones = [
            "Resume Playback",
            "Repeat playlist: ON" if self.repetir_playlist else "Repeat playlist: OFF",
            "Video",
            "ReplayGain: " + self.replaygain_mode.upper(),
            "Refresh nostrbit",
            "Refresh playlists",
            "Scan Wi-Fi",
            "Play snake",
            "IDLE",
            "Shutdown"
        ]
        seleccion = 0
        total = len(opciones)


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
                    self.refresh_display()
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
                    await self._menu_wifi(leer_entrada)
                    break 

                elif seleccion == 7:
                    from modules.snake_game import run_snake
                    await self.cerrar_menu_async()
                    await run_snake(self.lcd_interface)
                    # restaurar imagen del stream si estaba activo
                    self.refresh_display()
                    break
                
                elif seleccion == 8:
                    await self.cerrar_menu_async()
                    await self.enter_idle()
                    break
                
                elif seleccion == 9:
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



    async def _menu_wifi(self, leer_entrada):
        await self.cerrar_menu_async()
        self.en_menu = True

        img = self.lcd_interface.draw_text_on_lcd("Scanning...")
        self.lcd_interface.display_image(img)
        await asyncio.sleep(0.5)

        os.system("nmcli device wifi rescan")
        await asyncio.sleep(3)

        redes_raw = os.popen(
            "nmcli -t -f SSID,SIGNAL device wifi list"
        ).read().strip().splitlines()

        if not redes_raw:
            img = self.lcd_interface.draw_text_on_lcd("No networks found")
            self.lcd_interface.display_image(img)
            await asyncio.sleep(1.5)
            self.en_menu = False
            self.refresh_display()
            return

        redes = []
        for r in redes_raw:
            ssid, *signal = r.split(":")
            signal = signal[0] if signal else "?"
            redes.append(f"{ssid[:14]:14} {signal:>3}%")

        cursor_index = 0
        ventana_size = 8
        offset = 0

        while True:
            if cursor_index < offset:
                offset = cursor_index
            elif cursor_index >= offset + ventana_size:
                offset = cursor_index - ventana_size + 1

            lineas = []
            for i in range(offset, min(offset + ventana_size, len(redes))):
                prefijo = "> " if i == cursor_index else "  "
                lineas.append(prefijo + redes[i])

            titulo = f"Wi-Fi {cursor_index+1}/{len(redes)}"
            await self.mostrar_menu_async(
                lineas,
                cursor_index - offset,
                titulo=titulo
            )

            entrada = await leer_entrada()

            if entrada == "abajo":
                cursor_index = (cursor_index + 1) % len(redes)
            elif entrada == "arriba":
                cursor_index = (cursor_index - 1) % len(redes)
            elif entrada == "enter":
                ssid = redes_raw[cursor_index].split(":")[0]
                await self.conectar_wifi(ssid, leer_entrada)
                break
            elif entrada == "volver":
                break

        self.en_menu = False
        await self.cerrar_menu_async()
        self.refresh_display()



    async def conectar_wifi(self, ssid, leer_entrada):
        await self.cerrar_menu_async()
        self.en_menu = True

        img = self.lcd_interface.draw_text_on_lcd(f"Connecting\n{ssid}")
        self.lcd_interface.display_image(img)

        if self.existing_wifi_connection(ssid):
            # intentar levantar la conexión existente
            result = os.popen(f'sudo nmcli connection up "{ssid}"').read().lower()
            if "successfully activated" in result or "activated" in result:
                img = self.lcd_interface.draw_text_on_lcd("Connected!")
                self.lcd_interface.display_image(img)
                await asyncio.sleep(1.5)
                self.en_menu = False
                await self.cerrar_menu_async()
                self.refresh_display()
                return
            else:
                # si falla levantarla, borramos la conexión previa para rehacerla
                os.system(f'sudo nmcli connection delete "{ssid}"')

        # pedir contraseña
        password = await self.input_text(leer_entrada, titulo=f"{ssid} Password", oculto=False)
        if not password:
            self.en_menu = False
            self.refresh_display()
            return

        # crear la conexión de cero
        os.system(f'sudo nmcli device wifi connect "{ssid}" password "{password}"')
        os.system(f'sudo nmcli connection modify "{ssid}" connection.permissions "" connection.system yes')

        # intentar levantarla
        result = os.popen(f'sudo nmcli connection up "{ssid}"').read().lower()
        if "successfully activated" in result or "activated" in result:
            img = self.lcd_interface.draw_text_on_lcd("Connected!")
        else:
            img = self.lcd_interface.draw_text_on_lcd("Connection failed")
        self.lcd_interface.display_image(img)
        await asyncio.sleep(1.5)

        self.en_menu = False
        self.refresh_display()


    def existing_wifi_connection(self, ssid):
        try:
            # Solo obtenemos NAME y TYPE
            out = os.popen("nmcli -t -f NAME,TYPE connection show").read().splitlines()

            for line in out:
                parts = line.split(":")
                if len(parts) >= 2:
                    name, typ = parts[0], parts[1]
                    # Para Wi-Fi, el NAME suele ser el SSID
                    if typ == "wifi" and name == ssid:
                        return True
        except Exception:
            pass

        return False



    async def input_text(self, leer_entrada, titulo="Input", max_len=32, oculto=False):
        chars = list("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_@.")
        idx = 0
        texto = []

        self.en_menu = True

        while True:
            linea = "".join("*" if oculto else c for c in texto)
            cursor = chars[idx]

            display = [
                linea[:16],
                ("^ " + cursor)[:16]
            ]

            await self.mostrar_menu_async(display, 1, titulo=titulo)

            entrada = await leer_entrada()

            if entrada == "arriba":
                idx = (idx + 1) % len(chars)
            elif entrada == "abajo":
                idx = (idx - 1) % len(chars)
            elif entrada == "enter":
                if len(texto) < max_len:
                    texto.append(chars[idx])
            elif entrada == "enter_long":
                return "".join(texto)
            elif entrada == "extra":  # usar KEY extra como borrar
                if texto:
                    texto.pop()
            elif entrada == "volver":
                return None

        return "".join(texto)



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


            ###### --------------- CLOSE SYSTEM --------------- ######

    # detiene tareas y cierra mpv
    async def close(self):
        if self.update_task:
            self.update_task.cancel()
            try:
                await self.update_task
            except asyncio.CancelledError:
                pass
        await asyncio.to_thread(self.mpv_player.terminate)

