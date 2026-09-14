package engine

import (
	"context"
	"encoding/hex"
	"fmt"
	"sync"
	"time"

	"fiatjaf.com/nostr"
)

func (e *Engine) DebugDMHistory() {
	ctx, cancel := context.WithTimeout(
		context.Background(),
		15*time.Second,
	)
	defer cancel()

	myPubHex := hex.EncodeToString(e.Keys.Pub[:])

	filter := nostr.Filter{
		Kinds: []nostr.Kind{
			nostr.KindGiftWrap,
		},
		Tags: nostr.TagMap{
			"p": []string{myPubHex},
		},
	}

	var wg sync.WaitGroup

	fmt.Println("========================================")
	fmt.Println(" DEBUG NIP-17 HISTORY")
	fmt.Println("========================================")
	fmt.Println("Radiobit pubkey:", myPubHex)
	fmt.Println()

	for url, r := range e.Relays {
		wg.Add(1)

		go func(url string, r *nostr.Relay) {
			defer wg.Done()

			fmt.Println("========================================")
			fmt.Println("RELAY:", url)
			fmt.Println("========================================")

			sub, err := r.Subscribe(
				ctx,
				filter,
				nostr.SubscriptionOptions{},
			)
			if err != nil {
				fmt.Println("ERROR SUBSCRIBE:", err)
				return
			}

			count := 0
			decrypted := 0
			failed := 0

			for ev := range sub.Events {
				count++

				fmt.Printf(
					"\n1059 #%d\n",
					count,
				)
				fmt.Println("ID:", ev.ID)
				fmt.Println("GiftWrap PubKey:", ev.PubKey)
				fmt.Println("GiftWrap CreatedAt:", ev.CreatedAt)
				fmt.Println("Tags:", ev.Tags)

				sender, peer, msg, createdAt, err :=
					e.processGiftWrap(&ev)

				if err != nil {
					failed++
					fmt.Println("DECRYPT: FAILED")
					fmt.Println("ERROR:", err)
					continue
				}

				decrypted++

				fmt.Println("DECRYPT: OK")
				fmt.Println("Sender:", sender)
				fmt.Println("Peer:", peer)
				fmt.Println("Rumor CreatedAt:", createdAt)
				fmt.Println("Content:", msg)
			}

			fmt.Println()
			fmt.Println("----------------------------------------")
			fmt.Println("RESULTADO", url)
			fmt.Println("----------------------------------------")
			fmt.Println("1059 encontrados:", count)
			fmt.Println("Descifrados:", decrypted)
			fmt.Println("Fallidos:", failed)
			fmt.Println()
		}(url, r)
	}

	wg.Wait()

}
