package engine

import (
	"crypto/rand"
	"encoding/hex"
	"errors"

	"fiatjaf.com/nostr"
	"github.com/btcsuite/btcutil/bech32"
)

type KeyPair struct {
	Priv [32]byte
	Pub  [32]byte
}

func GenerateKeys() (*KeyPair, error) {
	var priv [32]byte
	_, err := rand.Read(priv[:])
	if err != nil {
		return nil, err
	}

	pub := nostr.GetPublicKey(priv)

	return &KeyPair{Priv: priv, Pub: pub}, nil
}

func LoadFromNsec(nsec string) (*KeyPair, error) {
	hrp, data, err := bech32.Decode(nsec)
	if err != nil {
		return nil, err
	}
	if hrp != "nsec" {
		return nil, errors.New("not nsec")
	}

	conv, err := bech32.ConvertBits(data, 5, 8, false)
	if err != nil {
		return nil, err
	}

	var priv [32]byte
	copy(priv[:], conv)

	pub := nostr.GetPublicKey(priv)

	return &KeyPair{Priv: priv, Pub: pub}, nil
}

func PubHex(pub [32]byte) string {
	return hex.EncodeToString(pub[:])
}
