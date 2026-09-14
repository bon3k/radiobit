package engine

import (
	"context"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"sort"
	"sync"
	"time"

	"fiatjaf.com/nostr"
	"fiatjaf.com/nostr/nip44"
)

// =====================================================
// OUTPUT UNICO
// =====================================================

type DMMessageOut struct {
	ID        string `json:"id"`
	Peer      string `json:"peer"`
	Sender    string `json:"sender"`
	Content   string `json:"content"`
	CreatedAt int64  `json:"created_at"`
}

// =====================================================
// SERIALIZER UNICO
// =====================================================

func MarshalDM(m DMMessageOut) ([]byte, error) {
	return json.Marshal(m)
}

// =====================================================
// EVENTOS YA PROCESADOS POR EL LISTENER
// =====================================================

var seenEvents sync.Map

// =====================================================
// SEND DM NIP-17
// =====================================================
//
//
// 1. rumor (kind 14)
// 2. seal (kind 13)
// 3. gift Wrap para el receptor (kind 1059)
// 4. gift Wrap para nosotros mismos (kind 1059)
//
// el gift Wrap propio permite recuperar
// los mensajes enviados desde el player
//
//
//
// el CreatedAt que representa el momento del mensaje es
// el del rumor, no el del Gift Wrap
//
// Los Gift Wraps tienen timestamps independientes
// =====================================================

func (e *Engine) SendDMNIP17(
	receiverHex string,
	msg string,
) (DMMessageOut, error) {

	// =====================================================
	// RECEPTOR
	// =====================================================

	var receiverPub nostr.PubKey

	hexBytes, err := hex.DecodeString(receiverHex)
	if err != nil {
		return DMMessageOut{}, fmt.Errorf(
			"invalid hex pubkey: %w",
			err,
		)
	}

	if len(hexBytes) != 32 {
		return DMMessageOut{}, fmt.Errorf(
			"invalid pubkey length: %d",
			len(hexBytes),
		)
	}

	copy(receiverPub[:], hexBytes)

	myPubHex := hex.EncodeToString(e.Keys.Pub[:])

	// =====================================================
	// RUMOR
	// =====================================================
	//
	//
	// el CreatedAt es el timestamp que se utilizar para
	// ordenar los mensajes en la conversacion
	//
	// el rumor no se firma.
	// =====================================================

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
		return DMMessageOut{}, err
	}

	// guarda el timestamp del rumor explicitamente
	// no utiliza el CreatedAt del gift Wrap
	createdAt := int64(rumor.CreatedAt)

	// =====================================================
	// SEAL
	// =====================================================

	convKey, err := nip44.GenerateConversationKey(
		receiverPub,
		e.Keys.Priv,
	)
	if err != nil {
		return DMMessageOut{}, err
	}

	encryptedRumor, err := nip44.Encrypt(
		string(rumorJSON),
		convKey,
	)
	if err != nil {
		return DMMessageOut{}, err
	}

	sealed := nostr.Event{
		Kind:      13,
		CreatedAt: nostr.Now(),
		PubKey:    e.Keys.Pub,
		Tags:      nostr.Tags{},
		Content:   encryptedRumor,
	}

	if err := sealed.Sign(e.Keys.Priv); err != nil {
		return DMMessageOut{}, err
	}

	sealedJSON, err := json.Marshal(sealed)
	if err != nil {
		return DMMessageOut{}, err
	}

	// =====================================================
	// GIFT WRAP PARA EL RECEPTOR
	// =====================================================

	ephemeralReceiver, err := GenerateKeys()
	if err != nil {
		return DMMessageOut{}, err
	}

	wrapKeyReceiver, err := nip44.GenerateConversationKey(
		receiverPub,
		ephemeralReceiver.Priv,
	)
	if err != nil {
		return DMMessageOut{}, err
	}

	wrappedReceiver, err := nip44.Encrypt(
		string(sealedJSON),
		wrapKeyReceiver,
	)
	if err != nil {
		return DMMessageOut{}, err
	}

	giftReceiver := nostr.Event{
		Kind:      nostr.KindGiftWrap,
		CreatedAt: nostr.Now(),
		PubKey:    ephemeralReceiver.Pub,
		Tags: nostr.Tags{
			{"p", receiverHex},
		},
		Content: wrappedReceiver,
	}

	if err := giftReceiver.Sign(ephemeralReceiver.Priv); err != nil {
		return DMMessageOut{}, err
	}

	// =====================================================
	// GIFT WRAP PARA EL PLAYER
	// =====================================================
	//
	//  FetchDMHistory() encuentra
	//  los mensajes enviados
	// =====================================================

	ephemeralSender, err := GenerateKeys()
	if err != nil {
		return DMMessageOut{}, err
	}

	wrapKeySender, err := nip44.GenerateConversationKey(
		e.Keys.Pub,
		ephemeralSender.Priv,
	)
	if err != nil {
		return DMMessageOut{}, err
	}

	wrappedSender, err := nip44.Encrypt(
		string(sealedJSON),
		wrapKeySender,
	)
	if err != nil {
		return DMMessageOut{}, err
	}

	giftSender := nostr.Event{
		Kind:      nostr.KindGiftWrap,
		CreatedAt: nostr.Now(),
		PubKey:    ephemeralSender.Pub,
		Tags: nostr.Tags{
			{"p", myPubHex},
		},
		Content: wrappedSender,
	}

	if err := giftSender.Sign(ephemeralSender.Priv); err != nil {
		return DMMessageOut{}, err
	}

	// =====================================================
	// EVITA QUE EL LISTENER DUPLIQUE
	// EL MENSAJE QUE SE ACABA DE ENVIAR
	// =====================================================

	seenEvents.Store(giftSender.ID, true)

	// =====================================================
	// PUBLICAR GIFT WRAP DEL RECEPTOR
	// =====================================================

	if err := e.publishToAllRelays(&giftReceiver); err != nil {
		return DMMessageOut{}, err
	}

	// =====================================================
	// PUBLICAR COPIA PARA RADIOBIT
	// =====================================================

	if err := e.publishToAllRelays(&giftSender); err != nil {
		return DMMessageOut{}, err
	}

	// =====================================================
	// RESULTADO PARA PYTHON
	// =====================================================
	//
	//
	// El ID que devuelve es el ID del gift wrap que se ha
	// publicado para el player
	//
	// =====================================================

	return DMMessageOut{
		ID:        fmt.Sprintf("%x", giftSender.ID[:]),
		Peer:      receiverHex,
		Sender:    myPubHex,
		Content:   msg,
		CreatedAt: createdAt,
	}, nil
}

// =====================================================
// LISTENER NIP-17
// =====================================================

func (e *Engine) ListenDMNIP17(
	handler func(msg DMMessageOut),
) error {

	ctx := context.Background()

	myPubHex := hex.EncodeToString(e.Keys.Pub[:])

	filter := nostr.Filter{
		Kinds: []nostr.Kind{
			nostr.KindGiftWrap,
		},
		Tags: nostr.TagMap{
			"p": []string{myPubHex},
		},
	}

	for url, r := range e.Relays {

		sub, err := r.Subscribe(
			ctx,
			filter,
			nostr.SubscriptionOptions{},
		)
		if err != nil {
			continue
		}

		go func(relay string, sub *nostr.Subscription) {

			fmt.Println("Listening:", relay)

			for ev := range sub.Events {

				if ev.Kind != nostr.KindGiftWrap ||
					len(ev.Content) < 10 {
					continue
				}

				// Evitar procesar dos veces el mismo gift wrap.
				if _, loaded := seenEvents.LoadOrStore(
					ev.ID,
					true,
				); loaded {
					continue
				}

				sender, peer, msg, createdAt, err :=
					e.processGiftWrap(&ev)

				if err != nil {
					continue
				}

				if peer == "" {
					peer = sender
				}

				out := DMMessageOut{
					ID:        fmt.Sprintf("%x", ev.ID[:]),
					Peer:      peer,
					Sender:    sender,
					Content:   msg,
					CreatedAt: createdAt,
				}

				handler(out)
			}

		}(url, sub)
	}

	return nil
}

// =====================================================
// HISTORY NIP-17
// =====================================================
//
// el gift wrap (kind 1059) esta firmado por una
// clave efímera
//
// el timestamp del Gift Wrap es deliberadamente
// aleatorio en NIP-17.
// =====================================================

func (e *Engine) FetchDMHistory() ([]DMMessageOut, error) {

	ctx, cancel := context.WithTimeout(
		context.Background(),
		10*time.Second,
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

	var mu sync.Mutex

	eventsMap := make(map[string]DMMessageOut)

	var wg sync.WaitGroup

	fetch := func(r *nostr.Relay) {

		defer wg.Done()

		sub, err := r.Subscribe(
			ctx,
			filter,
			nostr.SubscriptionOptions{},
		)
		if err != nil {
			return
		}

		for ev := range sub.Events {

			if ev.Kind != nostr.KindGiftWrap ||
				len(ev.Content) < 10 {
				continue
			}

			id := fmt.Sprintf("%x", ev.ID[:])

			// =================================================
			// EVITAR DUPLICADOS ENTRE RELAYS
			// =================================================

			mu.Lock()

			if _, exists := eventsMap[id]; exists {
				mu.Unlock()
				continue
			}

			mu.Unlock()

			// =================================================
			// DESCIFRAR
			// =================================================

			sender, peer, msg, createdAt, err :=
				e.processGiftWrap(&ev)

			if err != nil {
				continue
			}

			if peer == "" {
				peer = sender
			}

			out := DMMessageOut{
				ID:        id,
				Peer:      peer,
				Sender:    sender,
				Content:   msg,
				CreatedAt: createdAt,
			}

			// =================================================
			// GUARDAR
			// =================================================

			mu.Lock()

			if _, exists := eventsMap[id]; !exists {
				eventsMap[id] = out
			}

			mu.Unlock()
		}
	}

	// =====================================================
	// CONSULTAR TODOS LOS RELAYS
	// =====================================================

	for _, r := range e.Relays {

		wg.Add(1)

		go fetch(r)
	}

	wg.Wait()

	// =====================================================
	// CONVERTIR MAP A SLICE
	// =====================================================

	messages := make(
		[]DMMessageOut,
		0,
		len(eventsMap),
	)

	for _, m := range eventsMap {
		messages = append(messages, m)
	}

	// =====================================================
	// ORDEN CRONOLOGICO REAL
	// =====================================================

	sort.SliceStable(messages, func(i, j int) bool {

		if messages[i].CreatedAt == messages[j].CreatedAt {
			return messages[i].ID < messages[j].ID
		}

		return messages[i].CreatedAt < messages[j].CreatedAt
	})

	return messages, nil
}

// =====================================================
// DECRYPT GIFT WRAP
// =====================================================
//
// devuelve:
//
//     sender
//     peer
//     content
//     created_at
//
//
//
// mensaje recibido:
//
//     sender = contacto
//     peer   = player
//
// mensaje enviado:
//
//     sender = player
//     peer   = contacto
//
// =====================================================

func (e *Engine) processGiftWrap(
	gift *nostr.Event,
) (string, string, string, int64, error) {

	// =====================================================
	// DESCIFRAR GIFT WRAP -> SEAL
	// =====================================================

	convKey, err := nip44.GenerateConversationKey(
		gift.PubKey,
		e.Keys.Priv,
	)
	if err != nil {
		return "", "", "", 0, err
	}

	sealedJSON, err := nip44.Decrypt(
		gift.Content,
		convKey,
	)
	if err != nil {
		return "", "", "", 0, err
	}

	var sealed nostr.Event

	if err := json.Unmarshal(
		[]byte(sealedJSON),
		&sealed,
	); err != nil {
		return "", "", "", 0, err
	}

	realSender := sealed.PubKey

	// =====================================================
	// DESCIFRAR SEAL -> RUMOR
	// =====================================================

	convKey2, err := nip44.GenerateConversationKey(
		realSender,
		e.Keys.Priv,
	)
	if err != nil {
		return "", "", "", 0, err
	}

	rumorJSON, err := nip44.Decrypt(
		sealed.Content,
		convKey2,
	)
	if err != nil {
		return "", "", "", 0, err
	}

	var rumor nostr.Event

	if err := json.Unmarshal(
		[]byte(rumorJSON),
		&rumor,
	); err != nil {
		return "", "", "", 0, err
	}

	// =====================================================
	// IDENTIFICAR PEER DESDE EL RUMOR
	// =====================================================

	myPubHex := hex.EncodeToString(e.Keys.Pub[:])
	senderHex := hex.EncodeToString(realSender[:])

	peer := ""

	for _, t := range rumor.Tags {

		if len(t) < 2 {
			continue
		}

		if t[0] != "p" {
			continue
		}

		tagPub := t[1]

		// si el p apunta al player, entonces quien
		// ha enviado el mensaje es el peer

		if tagPub == myPubHex {
			if senderHex != myPubHex {
				peer = senderHex
			}
			continue
		}

		// si el p no apunta al player, es el destinatario
		// del mensaje enviado por el player

		peer = tagPub
		break
	}

	// =====================================================
	// FALLBACK
	// =====================================================

	if peer == "" && senderHex != myPubHex {
		peer = senderHex
	}

	// =====================================================
	// RESULTADO
	// =====================================================

	return senderHex, peer, rumor.Content, int64(rumor.CreatedAt), nil
}
