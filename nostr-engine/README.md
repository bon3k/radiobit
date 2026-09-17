# nostr-engine

This folder contains Go scripts for interacting with Nostr.

## Status
- Sending public events (Kind 1) is already functional.
- DM (NIP-17) is already functional.

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
git clone --depth 1 https://github.com/ggerganov/whisper.cpp.git
cd whisper.cpp
```

Compile whisper.cpp without the server:

```bash
cmake -B build -DWHISPER_BUILD_SERVER=OFF
cmake --build build --target whisper-cli
```

Download the base and tiny models:

```bash
cd models
bash download-ggml-model.sh base
bash download-ggml-model.sh tiny
```

Set NSEC key (it's better to create a new one for testing):

```bash
nano ~/.nostr_nsec
```

Paste your NSEC key, save, close and then change permissions:

```bash
chmod 600 ~/.nostr_nsec
```

