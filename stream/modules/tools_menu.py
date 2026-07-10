import asyncio
import os
import re
import subprocess

from modules.snake_game import run_snake


class Tools:

    def __init__(self, control):
        self.control = control

    async def menu(self, leer_entrada):
        await self.control.menu_simple(
            titulo="TOOLS",
            opciones=[
                "Refresh links",
                "Refresh playlists",
                "Reset mistouch",
                "Snake",
                "Show IP",
            ],
            callbacks=[
                self.refresh_nostrbit,
                self.refresh_playlists,
                self.reset_anti_mistouch,
                self.play_snake,
                self.show_ip,
            ],
            leer_entrada=leer_entrada
        )

    async def refresh_nostrbit(self):
        await self.control.cerrar_menu_async()

        img = self.control.lcd_interface.draw_text_on_lcd("Resolving...")
        self.control.lcd_interface.display_image(img)

        nuevos_streams = await self.control.resolve_all_npubs(
            self.control.load_streams("/home/radiobit/stream/data/streams.json")
        )

        self.control.streams = nuevos_streams

        img = self.control.lcd_interface.draw_text_on_lcd("Links updated")
        self.control.lcd_interface.display_image(img)

        await asyncio.sleep(1.5)

    async def refresh_playlists(self):
        await self.control.cerrar_menu_async()

        ruta_actual = (
            self.control.playlists[self.control.current_playlist][0]
            if self.control.playlists else None
        )

        pista_actual = self.control.mp3_actual()

        self.control.playlists = self.control.load_playlists(
            self.control.mp3_directory
        )

        nuevo_indice_playlist = 0
        nuevo_indice_pista = 0

        if ruta_actual:
            for i, (ruta, pistas) in enumerate(self.control.playlists):
                if ruta == ruta_actual:
                    nuevo_indice_playlist = i

                    if pista_actual:
                        try:
                            nuevo_indice_pista = pistas.index(pista_actual)
                        except ValueError:
                            nuevo_indice_pista = 0

                    break

        self.control.current_playlist = nuevo_indice_playlist

        self.control.playback_queue = (
            self.control.playlists[self.control.current_playlist][1]
            if self.control.playlists else []
        )

        self.control.current_mp3_index = (
            nuevo_indice_pista
            if self.control.playback_queue else 0
        )

        img = self.control.lcd_interface.draw_text_on_lcd(
            "Playlists updated"
        )

        self.control.lcd_interface.display_image(img)

        await asyncio.sleep(1.5)

    def _anti_mistouch_cmd(self, cmd):
        result = subprocess.run(
            f'echo "{cmd}" | nc -q 0 127.0.0.1 8423',
            shell=True,
            capture_output=True,
            text=True
        )

        return result.stdout.strip()

    async def reset_anti_mistouch(self):
        await self.control.cerrar_menu_async()

        img = self.control.lcd_interface.draw_text_on_lcd(
            "Reset touch..."
        )
        self.control.lcd_interface.display_image(img)

        try:
            self._anti_mistouch_cmd("set_anti_mistouch false")
            await asyncio.sleep(0.2)

            estado = self._anti_mistouch_cmd("get anti_mistouch")

            if "false" not in estado.lower():
                raise Exception()

            self._anti_mistouch_cmd("set_anti_mistouch true")
            await asyncio.sleep(0.2)

            estado = self._anti_mistouch_cmd("get anti_mistouch")

            if "true" not in estado.lower():
                raise Exception()

            img = self.control.lcd_interface.draw_text_on_lcd(
                "Touch reset OK"
            )

        except Exception:
            img = self.control.lcd_interface.draw_text_on_lcd(
                "Touch reset FAIL"
            )

        self.control.lcd_interface.display_image(img)

        await asyncio.sleep(1.5)

    async def play_snake(self):
        await self.control.cerrar_menu_async()

        await run_snake(self.control.lcd_interface)

        self.control.refresh_display()

    async def show_ip(self):
        await self.control.cerrar_menu_async()

        try:
            result = subprocess.check_output(
                "ip addr",
                shell=True
            ).decode()

            ips = re.findall(
                r'inet (\d+\.\d+\.\d+\.\d+)',
                result
            )

            ips = [
                ip for ip in ips
                if not ip.startswith("127.")
            ]

            ip_text = ips[0] if ips else "No IP"

        except Exception:
            ip_text = "Error IP"

        img = self.control.lcd_interface.draw_text_on_lcd(ip_text)

        self.control.lcd_interface.display_image(img)

        await asyncio.sleep(8)