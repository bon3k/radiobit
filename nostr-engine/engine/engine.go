package engine

import (
    "context"
    "time"

    "fiatjaf.com/nostr"
)

type Engine struct {
    Keys   *KeyPair
    Relays map[string]*nostr.Relay
}

func NewEngine(nsec string, relayURLs []string) (*Engine, error) {
    keys, err := LoadFromNsec(nsec)
    if err != nil {
        return nil, err
    }

    relays := make(map[string]*nostr.Relay)
    ctx := context.Background()
    for _, url := range relayURLs {
        r, err := nostr.RelayConnect(ctx, url, nostr.RelayOptions{})
        if err != nil {
            continue
        }
        relays[url] = r
    }

    return &Engine{
        Keys:   keys,
        Relays: relays,
    }, nil
}

func (e *Engine) NewEvent(kind nostr.Kind, content string, tags nostr.Tags) *nostr.Event {
    ev := nostr.Event{
        PubKey:    e.Keys.Pub,
        CreatedAt: nostr.Timestamp(time.Now().Unix()),
        Kind:      kind,
        Tags:      tags,
        Content:   content,
    }
    ev.Sign(e.Keys.Priv)
    return &ev
}

func (e *Engine) PublishEvent(ev *nostr.Event) error {
    return e.publishToAllRelays(ev)
}

