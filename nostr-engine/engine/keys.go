package engine

import (
	"crypto/rand"
	"encoding/hex"
	"errors"
	"os"
	"path/filepath"
	"strings"

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

// Cargar nsec desde ~/.nostr_nsec
func LoadNsecFromFile() (string, error) {
	home, err := os.UserHomeDir()
	if err != nil {
		return "", err
	}

	path := filepath.Join(home, ".nostr_nsec")

	data, err := os.ReadFile(path)
	if err != nil {
		return "", errors.New("no se pudo leer ~/.nostr_nsec")
	}

	nsec := strings.TrimSpace(string(data))
	if nsec == "" {
		return "", errors.New("~/.nostr_nsec está vacío")
	}

	return nsec, nil
}
