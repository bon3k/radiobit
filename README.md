# Radiobit

A DIY portable media device for local audio, video, internet radio, and Nostr streams.
Built on a Raspberry Pi Zero 2 with an LCD, physical controls, and a PiSugar3 battery pack.
It can be used as a standalone music player with headphones, or as a lightweight media server via its web app, allowing you to manage playlists, radio stations, Nostr keys, Wi-Fi connections, and stream audio and video directly from the browser.

---

## Installation

### Requirements

- Raspberry Pi Zero 2W
- 1.3" IPS LCD display HAT
- PiSugar 3 battery module
- BalenaEtcher or Raspberry Pi Imager

## Build

You can:
- Flash the SD card with the prebuilt image
- Or build it manually following the steps in [BUILD.md](./BUILD.md)

## Notes

- Open the web app at http://radiobit.local on your network.
Default password: radiobit.
- You can change the password by plugging a screen + keyboard into the Pi and running:

```bash
passwd
```
- There is also a PiSugar web app available at http://radiobit.local:8421.
The default user is `admin` and it has no password.
You can change both from the PiSugar web interface.
- The player was designed for the Pi Zero 2W, but works on any Raspberry Pi with the same LCD HAT.
- For big music libraries, copy files directly to the microSD instead of using the web app.
- Use a good microSD card (Class 10+) for best performance.

## Controls

| Button:                               | Action:                                                  |
|---------------------------------------|----------------------------------------------------------|
| **PiSugar (Short + long press)**      | Power on                                                 |
| **KEY1 (short press)**                | Change mode stream / mp3                                 |
| **KEY2 (short press)**                | Playlist menu                                            |
| **KEY3 (short press)**                | Track menu                                               |
| **KEY3 (Long press)**                 | System menu                                              |
| **Joystick (press)**                  | Confirm selection / pause                                |
| **Joystick (long press)**             | Confirm wifi password                                    |
| **Joystick (directions)**             | Navigate menus / change track / volume / move in game    |
| **KEY2 (short press, in game)**       | Restart game                                             |
| **KEY3 (short press, in game)**       | Quit game                                                |


---

Contributions and feedback are welcome — report bugs or feature requests in the [issues](https://github.com/bon3k/radiobit/issues) or submit a pull request.

