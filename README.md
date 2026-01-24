# Radiobit

A DIY music player for your own audio, internet radio, and Nostr streams. It runs on a Raspberry Pi Zero and comes with a small LCD screen, physical buttons, and a PiSugar3 battery pack. A simple web app lets you manage playlists, radio stations, Nostr public keys, and Wi-Fi settings.

---

## Installation

### Requirements

- Raspberry Pi Zero 2W
- 1.3" IPS LCD display HAT
- PiSugar 3 battery module
- BalenaEtcher or Raspberry Pi Imager

## Build

You can either:
- Flash the SD card with the prebuilt image
- Or build it manually following the steps in [BUILD.md](./BUILD.md)

## Notes

- Open the web app at http://radiobit.local on your network.
Default login: radiobit / radiobit.
- You can change the password by plugging a screen + keyboard into the Pi and running:

```bash
passwd
```

- Radiobit was designed for the Pi Zero 2W, but works on any Raspberry Pi with the same LCD HAT.
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
| **Joystick (directions)**             | Navigate menus / change track / volume / move in game    |
| **KEY2 (short press, in game)**       | Restart game                                             |
| **KEY3 (short press, in game)**       | Quit game                                                |


---

Contributions and feedback are welcome — report bugs or feature requests in the [issues](https://github.com/bon3k/radiobit/issues) or submit a pull request.

