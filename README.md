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

- Although it was designed for the **Raspberry Pi Zero 2W**, it can be built on any Raspberry Pi model as long as you use the same LCD HAT.
- If your **music library is very large**, it is recommended to copy the files directly to the microSD card from your computer, rather than uploading them through the web app.
- The web app is focused on handling Wi-Fi, playlists, radio links, and Nostr keys — not on heavy file management.
- For best performance, use a high-quality microSD card (Class 10 or better).

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

