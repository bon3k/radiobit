package engine

import (
	"context"
	"fmt"

	"fiatjaf.com/nostr"
)

func (e *Engine) publishToAllRelays(ev *nostr.Event) error {
	ctx := context.Background()
	if len(e.Relays) == 0 {
		return fmt.Errorf("no relays connected")
	}

	for _, r := range e.Relays {
		err := r.Publish(ctx, *ev)
		if err != nil {

		}
	}
	return nil
}

func (e *Engine) CloseRelays() {
	for _, r := range e.Relays {
		r.Close()
	}
}
