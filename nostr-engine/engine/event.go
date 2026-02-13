package engine

import (
	"time"

	"fiatjaf.com/nostr"
)

type EventBuilder struct {
	Priv [32]byte
	Pub  [32]byte
}

func NewEventBuilder(keys *KeyPair) *EventBuilder {
	return &EventBuilder{
		Priv: keys.Priv,
		Pub:  keys.Pub,
	}
}

func (b *EventBuilder) Build(kind nostr.Kind, content string, tags nostr.Tags) (*nostr.Event, error) {
	ev := nostr.Event{
		PubKey:    b.Pub,
		CreatedAt: nostr.Timestamp(time.Now().Unix()),
		Kind:      kind,
		Tags:      tags,
		Content:   content,
	}

	err := ev.Sign(b.Priv)
	if err != nil {
		return nil, err
	}

	return &ev, nil
}
