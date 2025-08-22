# Radiobit

Radiobit is a pocket-sized DIY player for MP3s, internet radio, and Nostr streams.
It runs on a Raspberry Pi Zero with a tiny LCD display, physical controls, and a PiSugar3 battery module, and is managed through a lightweight web app for playlists, radio links, Nostr public keys, and Wi-Fi.

---

## Installation

### Requirements

- Raspberry Pi Zero 2W
- 1.3" IPS LCD display HAT
- PiSugar 3 battery module
- BalenaEtcher or Raspberry Pi Imager

## Build

You can either:
- Flash the SD card with the prebuilt image (recommended)
- Or build it manually following the steps in [BUILD.md](./BUILD.md)

## First boot

On first boot, connect your Raspberry Pi to your router using an Ethernet-to-USB adapter.
This one-time wired connection is required to access the web app at http://radiobit.local, where you can configure Wi-Fi (either your home network or your phone’s hotspot).

## Notes

- Although Radiobit was designed for the **Raspberry Pi Zero 2W**, it can be built on any Raspberry Pi model as long as you use the same LCD HAT.
- If your **music library is very large**, it is recommended to copy the files directly to the microSD card from your computer, rather than uploading them through the web app.
- The web app is lightweight and simple, focused on handling Wi-Fi, playlists, radio links, and Nostr keys — not on heavy file management.
- For best performance, use high-quality microSD cards (Class 10 or better).

---

Contributions and feedback are welcome — report bugs or feature requests in the [issues](https://github.com/bon3k/radiobit/issues) or submit a pull request.

