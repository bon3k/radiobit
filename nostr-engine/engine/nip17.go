package engine

import (
        "encoding/json"
        "fmt"

        "fiatjaf.com/nostr"
        "fiatjaf.com/nostr/nip19"
        "fiatjaf.com/nostr/nip44"
)

func (e *Engine) SendDMNIP17(npub string, msg string) error {

        prefix, data, err := nip19.Decode(npub)
        if err != nil {
                return fmt.Errorf("error decodificando npub: %w", err)
        }
        if prefix != "npub" {
                return fmt.Errorf("no es un npub válido")
        }

        raw, ok := data.([]byte)
        if !ok || len(raw) != 32 {
                return fmt.Errorf("npub inválido")
        }

        var receiverPub nostr.PubKey
        copy(receiverPub[:], raw)

        sealed := nostr.Event{
                Kind:      13,
                CreatedAt: nostr.Now(),
                PubKey:    e.Keys.Pub,
                Content:   msg,
        }

        if err := sealed.Sign(e.Keys.Priv); err != nil {
                return fmt.Errorf("error firmando sealed event: %w", err)
        }

        sealedJSON, err := json.Marshal(sealed)
        if err != nil {
                return fmt.Errorf("error serializando sealed event: %w", err)
        }

        convKey, err := nip44.GenerateConversationKey(
                receiverPub,
                nostr.SecretKey(e.Keys.Priv),
        )
        if err != nil {
                return fmt.Errorf("error generando conversation key: %w", err)
        }

        encrypted, err := nip44.Encrypt(string(sealedJSON), convKey)
        if err != nil {
                return fmt.Errorf("error cifrando sealed event: %w", err)
        }

        gift := nostr.Event{
                Kind:      nostr.KindGiftWrap, // 1059
                CreatedAt: nostr.Now(),
                PubKey:    e.Keys.Pub,
                Tags: nostr.Tags{
                        {"p", receiverPub.String()},
                },
                Content: encrypted,
        }

        if err := gift.Sign(e.Keys.Priv); err != nil {
                return fmt.Errorf("error firmando giftwrap: %w", err)
        }

        return e.publishToAllRelays(&gift)
}
