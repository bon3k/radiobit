package engine

import (
        "context"
        "encoding/hex"
        "encoding/json"
        "fmt"
        "sync"

        "fiatjaf.com/nostr"
        "fiatjaf.com/nostr/nip44"
)

var seenEvents sync.Map

// =====================================================
// SEND DM (HEX ONLY)
// =====================================================
func (e *Engine) SendDMNIP17(receiverHex string, msg string) error {

        // -----------------------------
        // HEX -> PubKey
        // -----------------------------
        var receiverPub nostr.PubKey

        hexBytes, err := hex.DecodeString(receiverHex)
        if err != nil {
                return fmt.Errorf("invalid hex pubkey: %w", err)
        }
        copy(receiverPub[:], hexBytes)

        // -----------------------------
        // RUMOR (kind 14)
        // -----------------------------
        rumor := nostr.Event{
                Kind:      14,
                CreatedAt: nostr.Now(),
                PubKey:    e.Keys.Pub,
                Tags: nostr.Tags{
                        {"p", receiverHex},
                },
                Content: msg,
        }

        rumorJSON, err := json.Marshal(rumor)
        if err != nil {
                return err
        }

        // -----------------------------
        // NIP-44 ENCRYPT
        // -----------------------------
        convKey, err := nip44.GenerateConversationKey(receiverPub, e.Keys.Priv)
        if err != nil {
                return err
        }

        encryptedRumor, err := nip44.Encrypt(string(rumorJSON), convKey)
        if err != nil {
                return err
        }

        // -----------------------------
        // SEALED EVENT
        // -----------------------------
        sealed := nostr.Event{
                Kind:      13,
                CreatedAt: nostr.Now(),
                PubKey:    e.Keys.Pub,
                Content:   encryptedRumor,
        }

        if err := sealed.Sign(e.Keys.Priv); err != nil {
                return err
        }

        sealedJSON, err := json.Marshal(sealed)
        if err != nil {
                return err
        }

        // -----------------------------
        // EPHEMERAL KEY
        // -----------------------------
        ephemeral, err := GenerateKeys()
        if err != nil {
                return err
        }

        // -----------------------------
        // GIFTWRAP ENCRYPT
        // -----------------------------
        wrapKey, err := nip44.GenerateConversationKey(receiverPub, ephemeral.Priv)
        if err != nil {
                return err
        }

        wrappedContent, err := nip44.Encrypt(string(sealedJSON), wrapKey)
        if err != nil {
                return err
        }

        // -----------------------------
        // GIFT WRAP EVENT
        // -----------------------------
        gift := nostr.Event{
                Kind:      nostr.KindGiftWrap,
                CreatedAt: nostr.Now(),
                PubKey:    ephemeral.Pub,
                Tags: nostr.Tags{
                        {"p", receiverHex},
                },
                Content: wrappedContent,
        }

        if err := gift.Sign(ephemeral.Priv); err != nil {
                return err
        }

        // -----------------------------
        // PUBLISH
        // -----------------------------
        return e.publishToAllRelays(&gift)
}

// =====================================================
// LISTENER
// =====================================================
func (e *Engine) ListenDMNIP17(handler func(eventID string, sender string, msg string)) error {

        ctx := context.Background()

        filter := nostr.Filter{
                Kinds: []nostr.Kind{nostr.KindGiftWrap},
        }

        for url, r := range e.Relays {

                sub, err := r.Subscribe(ctx, filter, nostr.SubscriptionOptions{})
                if err != nil {
                        continue
                }

                go func(relay string, sub *nostr.Subscription) {

                        fmt.Println("Listening:", relay)

                        for ev := range sub.Events {

                                if ev.Kind != nostr.KindGiftWrap || len(ev.Content) < 10 {
                                        continue
                                }

                                if _, loaded := seenEvents.LoadOrStore(ev.ID, true); loaded {
                                        continue
                                }

                                sender, msg, err := e.processGiftWrap(&ev)
                                if err != nil {
                                        continue
                                }

                                handler(fmt.Sprintf("%x", ev.ID[:]), sender, msg)
                        }

                }(url, sub)
        }

        return nil
}

// =====================================================
// DECRYPT
// =====================================================
func (e *Engine) processGiftWrap(gift *nostr.Event) (string, string, error) {

        convKey, err := nip44.GenerateConversationKey(
                gift.PubKey,
                e.Keys.Priv,
        )
        if err != nil {
                return "", "", err
        }

        sealedJSON, err := nip44.Decrypt(gift.Content, convKey)
        if err != nil {
                return "", "", err
        }

        var sealed nostr.Event
        if err := json.Unmarshal([]byte(sealedJSON), &sealed); err != nil {
                return "", "", err
        }

        realSender := sealed.PubKey

        convKey2, err := nip44.GenerateConversationKey(
                realSender,
                e.Keys.Priv,
        )
        if err != nil {
                return "", "", err
        }

        rumorJSON, err := nip44.Decrypt(sealed.Content, convKey2)
        if err != nil {
                return "", "", err
        }

        var rumor nostr.Event
        if err := json.Unmarshal([]byte(rumorJSON), &rumor); err != nil {
                return "", "", err
        }

        return fmt.Sprintf("%x", realSender[:]), rumor.Content, nil
}
