import asyncio
import subprocess


class WifiMenu:
    def __init__(self, player):
        self.player = player


    async def menu(self, leer_entrada):
        player = self.player

        await player.cerrar_menu_async()
        player.en_menu = True

        img = player.lcd_interface.draw_text_on_lcd("Scanning...")
        player.lcd_interface.display_image(img)
        await asyncio.sleep(0.5)

        subprocess.run(
            ["nmcli", "device", "wifi", "rescan"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False
        )
        await asyncio.sleep(3)

        result = subprocess.run(
            ["nmcli", "-t", "-f", "SSID,SIGNAL", "device", "wifi", "list"],
            capture_output=True,
            text=True,
            check=False
        )

        redes_raw = result.stdout.strip().splitlines()

        if not redes_raw:
            img = player.lcd_interface.draw_text_on_lcd("No networks found")
            player.lcd_interface.display_image(img)
            await asyncio.sleep(1.5)
            player.en_menu = False
            player.refresh_display()
            return

        redes = []

        for red in redes_raw:
            ssid, *signal = red.split(":")
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

            for i in range(
                offset,
                min(offset + ventana_size, len(redes))
            ):
                prefijo = "> " if i == cursor_index else "  "
                lineas.append(prefijo + redes[i])

            titulo = f"Wi-Fi {cursor_index + 1}/{len(redes)}"

            await player.mostrar_menu_async(
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

        player.en_menu = False
        await player.cerrar_menu_async()
        player.refresh_display()


    async def conectar_wifi(self, ssid, leer_entrada):
        player = self.player

        await player.cerrar_menu_async()
        player.en_menu = True

        img = player.lcd_interface.draw_text_on_lcd(
            f"Connecting\n{ssid}"
        )
        player.lcd_interface.display_image(img)

        if self.existing_wifi_connection(ssid):
            result = subprocess.run(
                ["sudo", "nmcli", "connection", "up", ssid],
                capture_output=True,
                text=True,
                check=False
            )

            output = (result.stdout + result.stderr).lower()

            if "successfully activated" in output or "activated" in output:
                img = player.lcd_interface.draw_text_on_lcd("Connected!")
                player.lcd_interface.display_image(img)
                await asyncio.sleep(1.5)
                player.en_menu = False
                await player.cerrar_menu_async()
                player.refresh_display()
                return

            else:
                # elimina el perfil guardado si no consigue activarlo
                subprocess.run(
                    ["sudo", "nmcli", "connection", "delete", ssid],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False
                )

        password = await self.input_text(
            leer_entrada,
            titulo=f"{ssid} Password",
            oculto=False
        )

        if not password:
            player.en_menu = False
            player.refresh_display()
            return

        subprocess.run(
            [
                "sudo", "nmcli", "device", "wifi", "connect",
                ssid, "password", password
            ],
            capture_output=True,
            text=True,
            check=False
        )

        subprocess.run(
            [
                "sudo",
                "nmcli",
                "connection",
                "modify",
                ssid,
                "connection.permissions",
                "",
                "connection.system",
                "yes"
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False
        )

        result = subprocess.run(
            ["sudo", "nmcli", "connection", "up", ssid],
            capture_output=True,
            text=True,
            check=False
        )

        output = (result.stdout + result.stderr).lower()

        if "successfully activated" in output or "activated" in output:
            img = player.lcd_interface.draw_text_on_lcd("Connected!")
        else:
            img = player.lcd_interface.draw_text_on_lcd("Connection failed")

        player.lcd_interface.display_image(img)
        await asyncio.sleep(1.5)

        player.en_menu = False
        player.refresh_display()


    def existing_wifi_connection(self, ssid):
        try:
            result = subprocess.run(
                ["nmcli", "-t", "-f", "NAME,TYPE", "connection", "show"],
                capture_output=True,
                text=True,
                check=False
            )

            for line in result.stdout.splitlines():
                parts = line.split(":")

                if len(parts) >= 2:
                    name, tipo = parts[0], parts[1]

                    if tipo == "wifi" and name == ssid:
                        return True

        except Exception:
            pass

        return False


    async def input_text(
        self,
        leer_entrada,
        titulo="Input",
        max_len=32,
        oculto=False
    ):
        player = self.player

        chars = list(
            "abcdefghijklmnopqrstuvwxyz"
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            "0123456789-_@."
        )
        idx = 0
        texto = []

        player.en_menu = True

        while True:
            linea = "".join("*" if oculto else c for c in texto)
            cursor = chars[idx]

            display = [
                linea[-20:],
                ("^ " + cursor)[-20:]
            ]

            await player.mostrar_menu_async(
                display,
                1,
                titulo=titulo
            )

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

            elif entrada == "extra":
                if texto:
                    texto.pop()

            elif entrada == "volver":
                return None
