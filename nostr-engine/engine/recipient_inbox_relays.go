package engine

import (
	"context"
	"fmt"
	"time"

	"fiatjaf.com/nostr"
)

// obtiene relays de kind 10050 del receptor
func (e *Engine) GetInboxRelays(pub nostr.PubKey) ([]string, error) {

	ctx, cancel := context.WithTimeout(context.Background(), 12*time.Second)
	defer cancel()

	filter := nostr.Filter{
		Authors: []nostr.PubKey{pub},
		Kinds:   []nostr.Kind{10050},
		Limit:   1,
	}

	relaySet := make(map[string]bool)

	for url, r := range e.Relays {

		sub, err := r.Subscribe(ctx, filter, nostr.SubscriptionOptions{})
		if err != nil {
			fmt.Println("Error subscribing to relay", url, err)
			continue
		}

		// cerrar suscripcion
		defer sub.Close()

		for ev := range sub.Events {

			fmt.Println(">>> kind 10050 found on", url)
			fmt.Printf("    ID: %s\n", ev.ID)
			fmt.Printf("    CreatedAt: %d\n", ev.CreatedAt)
			fmt.Printf("    Tags: %v\n", ev.Tags)

			for _, tag := range ev.Tags {
				if len(tag) >= 2 && tag[0] == "relay" {

					relayURL := tag[1]

					// filtro de seguridad
					if len(relayURL) > 0 && (relayURL[:6] == "wss://" || relayURL[:5] == "ws://") {
						relaySet[relayURL] = true
					}
				}
			}
		}
	}

	// convertir a slice
	relays := []string{}
	for r := range relaySet {
		relays = append(relays, r)
	}

	if len(relays) == 0 {
		return nil, fmt.Errorf("no valid relays found in kind 10050")
	}

	return relays, nil
}
