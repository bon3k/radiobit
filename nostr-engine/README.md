# nostr-engine

This folder contains Go scripts for interacting with Nostr relays.

## Status
- Sending public events (Kind 1) is already functional.
- DM functionality (NIP-17) is not yet working.
- The python scripts in the main repo still need modifications to integrate the message menu.
- You can test it by replacing your current playback.py with the one provided in this folder.

## Future plans
- Complete integration of sending NIP-17 DMs through the player interface.
- Improve relay management and event publishing reliability.
- Testing and verification of NIP-44 encryption for DMs.

## Usage (standalone testing)

These commands allow you to test nostr-engine independently from the full player integration.

Send a public note:

```bash
go run main.go --nsec "your_nsec_here" send-public "hello there"
```

Send a DM (not functional yet):

```bash
go run main.go send-dm "destination_npub" "test DM message"
```

## Setup and compilation

This setup guide is intended for SSH usage. If you have already built everything manually, you’re all set. But if you flashed the .img, you’ll need to connect a keyboard and screen to enable SSH.

Follow these steps to prepare nostr-engine and whisper.cpp:

Boot the Raspberry Pi and connect:

```bash
ssh radiobit@radiobit.local
```

Install required dependencies:

```bash
sudo apt install golang-go cmake build-essential libomp-dev -y
```

Clone the repo and copy nostr-engine folder:

```bash
cd
git clone https://github.com/bon3k/radiobit.git
cd radiobit
cp -r nostr-engine /home/radiobit/stream/
cd /home/radiobit/stream/nostr-engine
```

Initialize Go module and tidy dependencies:

```bash
go mod tidy
go build
```

Clone whisper.cpp:

```bash
cd /home/radiobit/stream
git clone https://github.com/ggerganov/whisper.cpp.git
cd whisper.cpp
```

Compile whisper.cpp without the server:

```bash
cmake -B build -DWHISPER_BUILD_SERVER=OFF
cmake --build build --target whisper-cli
```

Download the base model:

```bash
cd models
bash download-ggml-model.sh base
```

If you prefer, you can download the `tiny` model instead.
The `base` model provides better accuracy but may be slower.


Set NSEC key (it's better to create a new one for testing):

```bash
nano ~/.nostr_nsec
```

Paste your NSEC key, save, close and then change permissions:

```bash
chmod 600 ~/.nostr_nsec
```

Replace script:

```bash
cd /home/radiobit/radiobit
cp nostr-engine/playback.py /home/radiobit/stream/modules
```

Default model language is English; to change it, edit /home/radiobit/stream/modules/playback.py, uncomment line 1336, and modify "-l", "es" to the language you want.
