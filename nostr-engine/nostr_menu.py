import os
import json
import time
import asyncio

from datetime import datetime


class NostrMenu:

    def __init__(self, player):

        self.player = player

        self.msg_state = 0
        self.recording_process = None
        self.voice_text = ""
        self.is_recording = False

        self.conv_cache = {}
        self.conv_queue = asyncio.Queue()

        # IDs de mensajes/eventos ya procesados
        # Evita que history-dm y listen-dm inserten dos veces el mismo mensaje
        self.seen_dm = set()

        self.my_pubkey = None

        self.nostr_proc = None


    ###### --------------- UTILS --------------- ######

    def norm_hex(self, h):
        return (h or "").lower().strip()


    def load_conversations_file(self):
        path = "/home/radiobit/stream/conversations.json"

        try:
            with open(path, "r") as f:
                return json.load(f)
        except:
            return {}


    async def get_my_pubkey(self):
        cmd = [
            "/home/radiobit/stream/nostr-engine/nostr-engine",
            "pubkey"
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            return None

        pubkey = stdout.decode().strip()

        if len(pubkey) != 64:
            return None

        return pubkey


    def init_conversations_cache(self):
        self.conv_cache = self.load_conversations_file()
        self.seen_dm = set()

        for messages in self.conv_cache.values():
            for msg in messages:
                event_id = self.norm_hex(msg.get("id"))
                if event_id:
                    self.seen_dm.add(f"id:{event_id}")


    def conversation_key(self, peer):
        """
        Identificador unico de conversacion

        la conversacion local siempre se agrupa
        por la pubkey del otro participante
        """
        return self.norm_hex(peer)


    def message_key(self, msg, peer, direction, text, timestamp=0):
        """
        Si el engine entrega un ID real del evento, usa ese ID.
        Si no, utiliza una combinacion de los datos disponibles
        """

        event_id = self.norm_hex(
            msg.get("id")
            or msg.get("event_id")
            or msg.get("event")
            or ""
        )

        if event_id:
            return f"id:{event_id}"

        return (
            f"fallback:"
            f"{self.norm_hex(peer)}:"
            f"{direction}:"
            f"{timestamp}:"
            f"{text}"
        )


    def register_seen_message(
        self,
        msg,
        peer,
        direction,
        text,
        timestamp=0
    ):
        key = self.message_key(
            msg,
            peer,
            direction,
            text,
            timestamp
        )

        if key in self.seen_dm:
            return False

        self.seen_dm.add(key)
        return True


    ###### --------------- SERVICES --------------- ######

    async def start_services(self):

        self.init_conversations_cache()

        self.my_pubkey = await self.get_my_pubkey()

        # Esto permite reconstruir el estado local al arrancar
#        await self.sync_nostr_history()


        # arranca servicios live
        asyncio.create_task(self.start_nostr_listener())
        asyncio.create_task(self.conversation_writer())


        # sincroniza history en segundo plano
        asyncio.create_task(self.sync_nostr_history())


    ###### --------------- HISTORY --------------- ######

    async def sync_nostr_history(self):

        cmd = [
            "/home/radiobit/stream/nostr-engine/nostr-engine",
            "history-dm"
        ]

#        print("DEBUG: ejecutando history-dm")

        try:

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=30
                )
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                    await proc.communicate()
                except Exception:
                    pass

                return

            if proc.returncode != 0:
                return

            lines = stdout.decode(errors="ignore").splitlines()

#            print("DEBUG: número de líneas:", len(lines))

            # guarda primero los mensajes history directamente en cache
            for line in lines:

                line = line.strip()

                if not line:
                    continue

                try:
                    msg = json.loads(line)
                except Exception:
                    continue

                await self.handle_history_dm(msg)

        except Exception:
            return


    async def handle_history_dm(self, msg):

        sender = self.norm_hex(
            msg.get("sender")
        )

        peer = self.norm_hex(
            msg.get("peer")
        )

        text = msg.get(
            "content",
            ""
        )

        timestamp = msg.get(
            "created_at",
            0
        )

        if not text:
            return

        # -------------------------------------------------
        # Determinar participante y direccion
        # -------------------------------------------------

        if not self.my_pubkey:
            return

        my_pubkey = self.norm_hex(
            self.my_pubkey
        )

        # esto evita duplicar la conversacion si se envia
        # un mensaje con la nscec local desde otro cliente

        if sender == my_pubkey and peer == my_pubkey:
            return


        if sender == my_pubkey:

            # Mensaje enviado por mi
            #
            # sender = my pubkey
            # peer   = destinatario
            #
            # La conversacion pertenece al destinatario

            conversation_peer = peer
            direction = "out"

        else:

            # Mensaje recibido
            #
            # sender = contact
            # peer   = my pubkey
            #
            # La conversacion pertenece al sender

            conversation_peer = sender
            direction = "in"

        if not conversation_peer:
            return

        conversation_peer = self.conversation_key(
            conversation_peer
        )

        # -------------------------------------------------
        # Deduplicacion
        # -------------------------------------------------

        if not self.register_seen_message(
            msg,
            conversation_peer,
            direction,
            text,
            timestamp
        ):
            return

        # -------------------------------------------------
        # Guardar en cache
        # -------------------------------------------------

        msg_id = self.norm_hex(msg.get("id"))

        if conversation_peer not in self.conv_cache:
            self.conv_cache[conversation_peer] = []

        self.conv_cache[conversation_peer].append(
            {
                "id": msg_id,
                "dir": direction,
                "text": text,
                "timestamp": timestamp
            }
        )

        # mantener orden cronologico
        self.conv_cache[conversation_peer].sort(
            key=lambda x: x.get(
                "timestamp",
                0
            )
        )

        # persistir history
        await self.write_conversations_snapshot()

    async def write_conversations_snapshot(self):

        path = "/home/radiobit/stream/conversations.json"

        try:

            snapshot = dict(self.conv_cache)

            with open(path, "w") as f:
                json.dump(
                    snapshot,
                    f
                )

        except Exception:
            pass


    ###### --------------- LISTENER --------------- ######

    async def start_nostr_listener(self):

        cmd = [
            "/home/radiobit/stream/nostr-engine/nostr-engine",
            "listen-dm"
        ]

        self.nostr_proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )


        async def read_stdout():

            while True:

                line = await self.nostr_proc.stdout.readline()

                if not line:
                    break

                try:

                    msg = json.loads(
                        line.decode().strip()
                    )

                    sender = self.norm_hex(
                        msg.get("sender")
                    )

                    text = msg.get(
                        "content",
                        ""
                    )

                    created_at = msg.get(
                        "created_at",
                        time.time()
                    )

                    if not sender or not text:
                        continue

                    await self.handle_incoming_dm(
                        sender,
                        text,
                        msg,
                        created_at
                    )

                except Exception:
                    continue


        async def read_stderr():

            while True:

                err = await self.nostr_proc.stderr.readline()

                if not err:
                    break

                # print("NOSTR ERR:", err.decode().strip())


        asyncio.create_task(read_stdout())
        asyncio.create_task(read_stderr())


    async def handle_incoming_dm(
        self,
        sender,
        text,
        msg=None,
        created_at=None
    ):

        sender = self.norm_hex(sender)

        if not sender or not text:
            return

        if sender == self.my_pubkey:
            return

        if msg is None:
            msg = {}

        if created_at is None:
            created_at = time.time()

        peer = self.conversation_key(
            sender
        )

        if not self.register_seen_message(
            msg,
            peer,
            "in",
            text,
            created_at
        ):
            return

        asyncio.create_task(
            self.save_message(
                peer,
                "in",
                text,
                created_at,
                msg.get("id", "")
            )
        )


    ###### --------------- STORAGE --------------- ######

    async def save_message(
        self,
        peer,
        direction,
        text,
        timestamp=None,
        msg_id=""
    ):

        peer = self.conversation_key(
            peer
        )

        if timestamp is None:
            timestamp = time.time()

        msg_id = self.norm_hex(msg_id)

        if msg_id:
            msg = {
                "id": msg_id
            }

            self.register_seen_message(
                msg,
                peer,
                direction,
                text,
                timestamp
            )

        await self.conv_queue.put(
            (
                peer,
                direction,
                text,
                timestamp,
                msg_id
            )
        )


    async def conversation_writer(self):

        path = "/home/radiobit/stream/conversations.json"

        while True:

            batch = []

            # -----------------------------
            # recoger mensajes
            # -----------------------------

            try:

                item = await asyncio.wait_for(
                    self.conv_queue.get(),
                    timeout=1.0
                )

                batch.append(item)

                while True:

                    try:

                        batch.append(
                            self.conv_queue.get_nowait()
                        )

                    except asyncio.QueueEmpty:
                        break

            except asyncio.TimeoutError:
                pass

            if not batch:
                continue

            # -----------------------------
            # actualizar cache
            # -----------------------------

            for item in batch:

                # compatibilidad con cualquier
                # entrada antigua de la queue
                if len(item) == 3:

                    peer, direction, text = item
                    timestamp = time.time()
                    msg_id = ""

                elif len(item) == 4:

                    peer, direction, text, timestamp = item
                    msg_id = ""

                else:

                    peer, direction, text, timestamp, msg_id = item

                peer = self.conversation_key(
                    peer
                )

                if peer not in self.conv_cache:
                    self.conv_cache[peer] = []

                self.conv_cache[peer].append(
                    {
                        "id": self.norm_hex(msg_id),
                        "dir": direction,
                        "text": text,
                        "timestamp": timestamp
                    }
                )

                self.conv_cache[peer].sort(
                    key=lambda x: x.get(
                        "timestamp",
                        0
                    )
                )

            # -----------------------------
            # escribir snapshot
            # -----------------------------

            try:

                snapshot = dict(
                    self.conv_cache
                )

                with open(path, "w") as f:

                    json.dump(
                        snapshot,
                        f
                    )

            except Exception:
                pass

            await asyncio.sleep(0)


    ###### --------------- MENU NOSTR --------------- ######

    async def menu_mensaje(self, leer_entrada):

        self.player.en_menu = True
        await self.player.pause_update_loop()

        opciones = [
            "Messages",
            "Write DM",
            "Public note (kind 1)",
            "Private note",
            "All notes"
        ]

        seleccion = 0
        total = len(opciones)

        while True:

            await self.player.mostrar_menu_async(
                opciones,
                seleccion,
                titulo="NOSTR DM"
            )

            entrada = await leer_entrada()

            if entrada == "abajo":
                seleccion = (
                    seleccion + 1
                ) % total

            elif entrada == "arriba":
                seleccion = (
                    seleccion - 1
                ) % total

            elif entrada == "enter":

                if seleccion == 0:
                    await self.menu_messages(
                        leer_entrada
                    )

                elif seleccion == 1:
                    await self.menu_write_msg(
                        leer_entrada
                    )

                elif seleccion == 2:
                    await self.menu_publish(
                        leer_entrada
                    )

                elif seleccion == 3:
                    await self.menu_private_note(
                        leer_entrada
                    )

                elif seleccion == 4:
                    await self.menu_private_notes(
                        leer_entrada
                    )

            elif entrada == "volver":
                break

        self.player.en_menu = False
        self.player.resume_update_loop()

        await self.player.cerrar_menu_async()
        self.player.refresh_display()


    async def menu_messages(self, leer_entrada):

        data = self.conv_cache

        if not data:

            img = self.player.lcd_interface.draw_text_on_lcd(
                "No messages"
            )

            self.player.lcd_interface.display_image(
                img
            )

            await asyncio.sleep(1.5)
            return

        contactos = self.load_contacts()

        contact_map = {}

        for c in contactos:

            hexpk = (
                c.get("hex") or ""
            ).lower().strip()

            name = c.get(
                "name",
                ""
            )

            if hexpk:
                contact_map[hexpk] = name

        seleccion = 0

        while True:

            labels = []

            peers = list(
                data.keys()
            )

            for peer in peers:

                msgs = data.get(
                    peer,
                    []
                )

                name = contact_map.get(
                    peer,
                    peer[:8]
                )

                if msgs:

                    last_msg = msgs[-1]

                    prefix = (
                        "You"
                        if last_msg["dir"] == "out"
                        else name
                    )

                    last = (
                        f"{prefix}: "
                        f"{last_msg['text'][:20]}"
                    )

                else:
                    last = ""

                labels.append(
                    last
                )

            if not peers:
                return

            if seleccion >= len(peers):
                seleccion = len(peers) - 1

            await self.player.mostrar_menu_async(
                labels,
                seleccion,
                titulo="MESSAGES"
            )

            entrada = await leer_entrada()

            if entrada == "abajo":

                seleccion = (
                    seleccion + 1
                ) % len(peers)

            elif entrada == "arriba":

                seleccion = (
                    seleccion - 1
                ) % len(peers)

            elif entrada == "enter":

                await self.open_conversation(
                    peers[seleccion],
                    leer_entrada
                )

            elif entrada == "volver":
                break


    async def open_conversation(
        self,
        peer,
        leer_entrada
    ):

        contactos = self.load_contacts()

        hexpk = self.conversation_key(
            peer
        )

        name = next(
            (
                c["name"]
                for c in contactos
                if (
                    c.get("hex") or ""
                ).lower().strip() == hexpk
            ),
            hexpk[:8]
        )

        data = self.conv_cache.get(
            hexpk,
            []
        )

        if not data:

            img = self.player.lcd_interface.draw_text_on_lcd(
                "Empty chat"
            )

            self.player.lcd_interface.display_image(
                img
            )

            await asyncio.sleep(1.5)
            return

        # ---- construir bloques UNA VEZ ----

        blocks = self.player.lcd_interface.build_chat_blocks(
            data,
            name
        )

        viewport = (
            self.player.lcd_interface
            .get_chat_viewport()
        )

        max_scroll = (
            self.player.lcd_interface
            .get_chat_scroll_limits(
                blocks,
                viewport
            )
        )

        # empieza abajo

        scroll_offset = max_scroll

        # ---- control de cambios ----

        last_len = len(data)
        cached_img = None
        last_scroll = -1

        while True:

            new_data = self.conv_cache.get(
                hexpk,
                []
            )

            # ---- si hay nuevos mensajes ----

            if len(new_data) != last_len:

                data = new_data
                last_len = len(new_data)

                blocks = (
                    self.player.lcd_interface
                    .build_chat_blocks(
                        data,
                        name
                    )
                )

                max_scroll = (
                    self.player.lcd_interface
                    .get_chat_scroll_limits(
                        blocks,
                        viewport
                    )
                )

                # autoscroll si esta abajo del todo

                if scroll_offset >= max_scroll - 2:
                    scroll_offset = max_scroll

                # forzar redraw

                cached_img = None

            # ---- render solo si cambia algo ----

            if (
                scroll_offset != last_scroll
                or cached_img is None
            ):

                cached_img = (
                    self.player.lcd_interface
                    .draw_chat_feed(
                        blocks,
                        scroll_offset
                    )
                )

                last_scroll = scroll_offset

            self.player.lcd_interface.display_image(
                cached_img
            )

            entrada = await leer_entrada()

            if entrada == "abajo":

                scroll_offset = min(
                    scroll_offset + 1,
                    max_scroll
                )

            elif entrada == "arriba":

                scroll_offset = max(
                    scroll_offset - 1,
                    0
                )

            elif entrada == "volver":
                break

            await asyncio.sleep(0.01)


    ###### --------------- PUBLIC NOTE --------------- ######

    async def menu_publish(self, leer_entrada):

        self.reset_msg_state()
        self.player.en_menu = True

        img = self.player.lcd_interface.draw_text_on_lcd(
            "Push to record"
        )

        self.player.lcd_interface.display_image(img)

        while True:

            entrada = await leer_entrada()

            if entrada == "enter":

                if self.msg_state == 0:

                    img = self.player.lcd_interface.draw_text_on_lcd(
                        "Recording...\nPush to stop"
                    )

                    self.player.lcd_interface.display_image(
                        img
                    )

                    await self.start_recording()

                    self.msg_state = 1

                elif self.msg_state == 1:

                    await self.stop_recording()

                    img = self.player.lcd_interface.draw_text_on_lcd(
                        "Transcribing..."
                    )

                    self.player.lcd_interface.display_image(
                        img
                    )

                    self.msg_state = 2

                    text = await self.transcribe_voice()

                    if not text:

                        img = self.player.lcd_interface.draw_text_on_lcd(
                            "No voice text"
                        )

                        self.player.lcd_interface.display_image(
                            img
                        )

                        await asyncio.sleep(1.5)
                        break

                    self.msg_state = 3

                    img = self.player.lcd_interface.draw_chat_on_lcd(
                        text
                    )

                    self.player.lcd_interface.display_image(
                        img
                    )

                elif self.msg_state == 3:

                    img = self.player.lcd_interface.draw_text_on_lcd(
                        "Publishing..."
                    )

                    self.player.lcd_interface.display_image(
                        img
                    )

                    await self.publish_voice()

                    img = self.player.lcd_interface.draw_text_on_lcd(
                        "Sent ✔"
                    )

                    self.player.lcd_interface.display_image(
                        img
                    )

                    await asyncio.sleep(1.5)

                    self.reset_msg_state()
                    break

            elif entrada == "volver":
                break

        self.reset_msg_state()

        self.player.en_menu = False

        await self.player.cerrar_menu_async()

        return


    ###### --------------- PRIVATE NOTE --------------- ######

    async def menu_private_note(self, leer_entrada):

        self.reset_msg_state()
        self.player.en_menu = True

        img = self.player.lcd_interface.draw_text_on_lcd(
            "Push to record"
        )

        self.player.lcd_interface.display_image(img)

        while True:

            entrada = await leer_entrada()

            if entrada == "enter":

                if self.msg_state == 0:

                    img = self.player.lcd_interface.draw_text_on_lcd(
                        "Recording...\nPush to stop"
                    )

                    self.player.lcd_interface.display_image(
                        img
                    )

                    await self.start_recording()

                    self.msg_state = 1

                elif self.msg_state == 1:

                    await self.stop_recording()

                    img = self.player.lcd_interface.draw_text_on_lcd(
                        "Transcribing..."
                    )

                    self.player.lcd_interface.display_image(
                        img
                    )

                    self.msg_state = 2

                    text = await self.transcribe_voice()

                    if not text:

                        img = self.player.lcd_interface.draw_text_on_lcd(
                            "No voice text"
                        )

                        self.player.lcd_interface.display_image(
                            img
                        )

                        await asyncio.sleep(1.5)
                        break

                    self.msg_state = 3

                    img = self.player.lcd_interface.draw_chat_on_lcd(
                        text
                    )

                    self.player.lcd_interface.display_image(
                        img
                    )

                elif self.msg_state == 3:

                    img = self.player.lcd_interface.draw_text_on_lcd(
                        "Saving..."
                    )

                    self.player.lcd_interface.display_image(
                        img
                    )

                    await self.save_private_note()

                    img = self.player.lcd_interface.draw_text_on_lcd(
                        "Saved ✔"
                    )

                    self.player.lcd_interface.display_image(
                        img
                    )

                    await asyncio.sleep(1.5)

                    self.reset_msg_state()
                    break

            elif entrada == "volver":
                break

        self.reset_msg_state()

        self.player.en_menu = False

        await self.player.cerrar_menu_async()

        return


    async def menu_private_notes(self, leer_entrada):

        notes = self.load_private_notes()

        if not notes:

            img = self.player.lcd_interface.draw_text_on_lcd(
                "No private notes"
            )

            self.player.lcd_interface.display_image(
                img
            )

            await asyncio.sleep(1.5)
            return

        seleccion = len(notes) - 1

        while True:

            MAX_CHARS = 25

            labels = []

            for note in notes:

                lines = note.split("\n")

                if len(lines) >= 2:

                    text = " ".join(
                        lines[1:]
                    ).strip()

                else:

                    text = note.strip()

                if len(text) > MAX_CHARS:

                    text = (
                        text[:MAX_CHARS - 3]
                        .rstrip()
                        + "..."
                    )

                labels.append(text)

            await self.player.mostrar_menu_async(
                labels,
                seleccion,
                titulo="PRIVATE NOTES"
            )

            entrada = await leer_entrada()

            if entrada == "abajo":

                seleccion = (
                    seleccion + 1
                ) % len(notes)

            elif entrada == "arriba":

                seleccion = (
                    seleccion - 1
                ) % len(notes)

            elif entrada == "enter":

                await self.open_private_note(
                    notes[seleccion],
                    leer_entrada
                )

            elif entrada == "volver":
                break


    async def save_private_note(self):

        if not self.voice_text:
            return

        notes_dir = "/home/radiobit/stream/data/z-notes"

        try:
            os.makedirs(notes_dir, exist_ok=True)

            timestamp = time.strftime(
                "%Y-%m-%d %H:%M:%S"
            )

            filename = time.strftime(
                "%Y-%m-%d_%H-%M-%S.txt"
            )

            path = os.path.join(
                notes_dir,
                filename
            )

            # evitar colisiones
            counter = 1

            while os.path.exists(path):
                filename = time.strftime(
                    "%Y-%m-%d_%H-%M-%S"
                ) + f"_{counter}.txt"

                path = os.path.join(
                    notes_dir,
                    filename
                )

                counter += 1

            with open(path, "w") as f:

                f.write(
                    f"[{timestamp}]\n"
                )

                f.write(
                    self.voice_text.strip()
                )

        except Exception:
            pass

        
    def load_private_notes(self):

        notes_dir = "/home/radiobit/stream/data/z-notes"

        try:
            if not os.path.exists(notes_dir):
                return []

            notes = []

            for filename in os.listdir(notes_dir):

                if not filename.endswith(".txt"):
                    continue

                path = os.path.join(
                    notes_dir,
                    filename
                )

                try:
                    with open(path, "r") as f:
                        content = f.read().strip()

                    if content:
                        notes.append(content)

                except Exception:
                    continue

            # orden cronologico por nombre
            notes.sort()

            return notes

        except Exception:
            return []


    async def open_private_note(
        self,
        note,
        leer_entrada
    ):

        lines = note.split("\n")

        if lines:

            timestamp = lines[0]

            if (
                timestamp.startswith("[")
                and timestamp.endswith("]")
            ):

                timestamp = datetime.strptime(
                    timestamp[1:-1],
                    "%Y-%m-%d %H:%M:%S"
                ).strftime(
                    "[%Y-%m-%d %H:%M]"
                )

            content = "\n".join(
                lines[1:]
            ).strip()

            note = (
                f"{timestamp}\n\n"
                f"{content}"
            )

        mensajes = [
            {
                "dir": "in",
                "text": note
            }
        ]

        blocks = (
            self.player.lcd_interface
            .build_chat_blocks(
                mensajes,
                ""
            )
        )

        viewport = (
            self.player.lcd_interface
            .get_chat_viewport()
        )

        max_scroll = (
            self.player.lcd_interface
            .get_chat_scroll_limits(
                blocks,
                viewport
            )
        )

        scroll_offset = 0
        last_scroll = -1
        cached_img = None

        while True:

            if (
                scroll_offset != last_scroll
                or cached_img is None
            ):

                cached_img = (
                    self.player.lcd_interface
                    .draw_chat_feed(
                        blocks,
                        scroll_offset
                    )
                )

                last_scroll = scroll_offset

            self.player.lcd_interface.display_image(
                cached_img
            )

            entrada = await leer_entrada()

            if entrada == "abajo":

                scroll_offset = min(
                    scroll_offset + 1,
                    max_scroll
                )

            elif entrada == "arriba":

                scroll_offset = max(
                    scroll_offset - 1,
                    0
                )

            elif entrada == "volver":
                break

            await asyncio.sleep(0.01)


    ###### --------------- RECORDING --------------- ######

    async def start_recording(self):

        self.is_recording = True
        self.voice_text = ""

        cmd = [
            "arecord",
            "-D", "hw:0,0",
            "-f", "S16_LE",
            "-r", "16000",
            "-c", "1",
            "/tmp/radiobit_voice.wav"
        ]

        self.recording_process = (
            await asyncio.create_subprocess_exec(
                *cmd
            )
        )


    async def stop_recording(self):

        if self.recording_process:

            self.recording_process.terminate()

            await self.recording_process.wait()

            self.recording_process = None

        self.is_recording = False


    async def transcribe_voice(self):

        img = self.player.lcd_interface.draw_text_on_lcd(
            "Transcribing..."
        )

        self.player.lcd_interface.display_image(
            img
        )

        base_model = (
            "/home/radiobit/stream/"
            "whisper.cpp/models/ggml-base.bin"
        )

        tiny_model = (
            "/home/radiobit/stream/"
            "whisper.cpp/models/ggml-tiny.bin"
        )

        USE_TINY_MODEL = True               ##  <---- change whisper model     ####

        if USE_TINY_MODEL:

            preferred = tiny_model
            fallback = base_model

        else:

            preferred = base_model
            fallback = tiny_model

        if os.path.exists(preferred):

            model_path = preferred

        elif os.path.exists(fallback):

            model_path = fallback

        else:

            self.voice_text = ""
            return ""

        cmd = [
            "/home/radiobit/stream/"
            "whisper.cpp/build/bin/whisper-cli",
            "-m", model_path,
            "-f", "/tmp/radiobit_voice.wav",
            "-l", "es",
            "-otxt"
        ]

        try:

            proc = await asyncio.create_subprocess_exec(
                *cmd
            )

            try:

                await asyncio.wait_for(
                    proc.wait(),
                    timeout=60
                )

            except asyncio.TimeoutError:

                try:

                    proc.terminate()

                    await asyncio.sleep(1)

                    if proc.returncode is None:
                        proc.kill()

                except Exception:
                    pass

                self.voice_text = ""
                return ""

        except Exception:

            self.voice_text = ""
            return ""

        if proc.returncode != 0:

            self.voice_text = ""
            return ""

        try:

            with open(
                "/tmp/radiobit_voice.wav.txt"
            ) as f:

                self.voice_text = (
                    f.read().strip()
                )

        except Exception:

            self.voice_text = ""

        return self.voice_text


    async def publish_voice(self):

        if not self.voice_text:
            return

        safe_text = (
            self.voice_text
            .replace('"', "'")
        )

        cmd = [
            "/home/radiobit/stream/"
            "nostr-engine/nostr-engine",
            "send-public",
            safe_text
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await proc.communicate()


    ###### --------------- DIRECT MESSAGES --------------- ######

    def load_contacts(self):

        try:

            with open(
                "/home/radiobit/stream/contacts.json"
            ) as f:

                return json.load(f)

        except:

            return []


    async def menu_write_msg(
        self,
        leer_entrada
    ):

        contactos = self.load_contacts()

        if not contactos:

            img = self.player.lcd_interface.draw_text_on_lcd(
                "No contacts"
            )

            self.player.lcd_interface.display_image(
                img
            )

            await asyncio.sleep(1.5)
            return

        seleccion = 0
        total = len(contactos)

        while True:

            nombres = [
                c["name"]
                for c in contactos
            ]

            await self.player.mostrar_menu_async(
                nombres,
                seleccion,
                titulo="CONTACTS"
            )

            entrada = await leer_entrada()

            if entrada == "abajo":

                seleccion = (
                    seleccion + 1
                ) % total

            elif entrada == "arriba":

                seleccion = (
                    seleccion - 1
                ) % total

            elif entrada == "enter":

                contacto = contactos[
                    seleccion
                ]

                await self.menu_write_msg_record(
                    leer_entrada,
                    contacto
                )

                break

            elif entrada == "volver":
                break


    async def menu_write_msg_record(
        self,
        leer_entrada,
        contacto
    ):

        self.reset_msg_state()

        self.player.en_menu = True

        img = self.player.lcd_interface.draw_text_on_lcd(
            f"{contacto['name']}\nPush to record"
        )

        self.player.lcd_interface.display_image(
            img
        )

        while True:

            entrada = await leer_entrada()

            if entrada == "enter":

                if self.msg_state == 0:

                    img = self.player.lcd_interface.draw_text_on_lcd(
                        "Recording...\nPush to stop"
                    )

                    self.player.lcd_interface.display_image(
                        img
                    )

                    await self.start_recording()

                    self.msg_state = 1

                elif self.msg_state == 1:

                    await self.stop_recording()

                    img = self.player.lcd_interface.draw_text_on_lcd(
                        "Transcribing..."
                    )

                    self.player.lcd_interface.display_image(
                        img
                    )

                    self.msg_state = 2

                    text = await self.transcribe_voice()

                    if not text:

                        img = self.player.lcd_interface.draw_text_on_lcd(
                            "No voice text"
                        )

                        self.player.lcd_interface.display_image(
                            img
                        )

                        await asyncio.sleep(1.5)
                        break

                    self.msg_state = 3

                    img = self.player.lcd_interface.draw_chat_on_lcd(
                        text
                    )

                    self.player.lcd_interface.display_image(
                        img
                    )

                elif self.msg_state == 3:

                    img = self.player.lcd_interface.draw_text_on_lcd(
                        "Sending DM..."
                    )

                    self.player.lcd_interface.display_image(
                        img
                    )

                    text = self.voice_text

                    # ---------------------------------------
                    # Enviar mediante el engine NIP-17
                    # ---------------------------------------

                    sent_msg = await self.send_dm_voice(
                        contacto["hex"]
                    )

                    if not sent_msg:
                        img = self.player.lcd_interface.draw_text_on_lcd(
                            "Send failed"
                        )
                        self.player.lcd_interface.display_image(img)
                        await asyncio.sleep(1.5)
                        break

                    peer = self.conversation_key(
                        contacto["hex"]
                    )

                    await self.save_message(
                        peer,
                        "out",
                        text,
                        sent_msg.get("created_at", time.time()),
                        sent_msg.get("id", "")
                    )

                    img = self.player.lcd_interface.draw_text_on_lcd(
                        "Sent ✔"
                    )

                    self.player.lcd_interface.display_image(
                        img
                    )

                    await asyncio.sleep(1.5)

                    break

            elif entrada == "volver":
                break

        self.reset_msg_state()

        self.player.en_menu = False

        await self.player.cerrar_menu_async()


    async def send_dm_voice(self, hexpk):

        if not self.voice_text:
            return None

        safe_text = (
            self.voice_text
            .replace('"', "'")
        )

        cmd = [
            "/home/radiobit/stream/"
            "nostr-engine/nostr-engine",
            "send-dm",
            hexpk,
            safe_text
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        try:

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=15
            )

        except asyncio.TimeoutError:

            proc.kill()
            await proc.communicate()

            print("DM timeout")
            return None

        if proc.returncode != 0:
            return None

        try:
            return json.loads(
                stdout.decode(errors="ignore").strip()
            )

        except Exception:
            return None


    ###### --------------- RESET --------------- ######

    def reset_msg_state(self):

        self.msg_state = 0
        self.voice_text = ""
        self.is_recording = False

        try:
            os.remove(
                "/tmp/radiobit_voice.wav"
            )
        except:
            pass

        try:
            os.remove(
                "/tmp/radiobit_voice.wav.txt"
            )
        except:
            pass
