# nostr-engine

This folder contains Go scripts for interacting with Nostr relays.

## Status
- Partially integrated in the player dev version.
- Sending public events (Kind 1) is already functional.
- DM functionality (NIP-17) is not yet working.
- The python scripts in the main repo still need modifications to integrate the message menu and call nostr-engine.

## Future plans
- Complete integration of sending NIP-17 DMs through the player interface.
- Improve relay management and event publishing reliability.
- Testing and verification of NIP-44 encryption for DMs.
- Documentation and examples for using nostr-engine within radiobit.

## Usage (basic)

Set your NSEC key:

```bash
export NOSTR_NSEC=<your_nsec_here>
```

Send a public note:

```bash
go run main.go send-public "hello there"
```

Send a DM (not functional yet):

```bash
go run main.go send-dm <npub> "test DM message"
```
