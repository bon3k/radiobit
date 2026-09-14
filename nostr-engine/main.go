package main

import (
	"flag"
	"fmt"
	"os"

	"nostr-engine/engine"
)

func main() {
	nsecFlag := flag.String("nsec", "", "nsec key")
	flag.Parse()

	args := flag.Args()

	if len(args) < 1 {
		fmt.Println("use: send-public <msg> | send-dm <hex> <msg> | listen-dm | history-dm")
		return
	}

	// -----------------------------
	// KEY LOADING
	// -----------------------------
	nsec := *nsecFlag

	if nsec == "" {
		nsec = os.Getenv("NOSTR_NSEC")
	}

	if nsec == "" {
		var err error
		nsec, err = engine.LoadNsecFromFile()
		if err != nil {
			fmt.Println("Nsec not found")
			return
		}
	}

	// -----------------------------
	// RELAYS
	// -----------------------------
	relays := []string{
		"wss://nos.lol",
		"wss://relay.damus.io",
		"wss://relay.0xchat.com",
	}

	eng, err := engine.NewEngine(nsec, relays)
	if err != nil {
		fmt.Println("Error creating engine:", err)
		return
	}

	// -----------------------------
	// COMMANDS
	// -----------------------------
	switch args[0] {

	case "debug-history":
		eng.DebugDMHistory()

        case "pubkey":
                fmt.Println(engine.PubHex(eng.Keys.Pub))

	case "inbox-relays":
		relays, err := eng.GetInboxRelays(eng.Keys.Pub)
		if err != nil {
			fmt.Println("ERROR:", err)
			return
		}

		fmt.Println("Inbox relays:")
		for _, relay := range relays {
			fmt.Println(" ", relay)
		}

	case "send-public":
		if len(args) < 2 {
			fmt.Println("use: send-public <msg>")
			return
		}

		ev := eng.NewEvent(1, args[1], nil)
		if err := eng.PublishEvent(ev); err != nil {
			fmt.Println("Error publishing:", err)
		}

	case "send-dm":
		if len(args) < 3 {
			fmt.Println("use: send-dm <hex> <msg>")
			return
		}

		msg, err := eng.SendDMNIP17(args[1], args[2])
		if err != nil {
			fmt.Println("ERROR:", err)
			return
		}

		b, _ := engine.MarshalDM(msg)
		fmt.Println(string(b))

	case "listen-dm":

		err := eng.ListenDMNIP17(func(msg engine.DMMessageOut) {
			b, _ := engine.MarshalDM(msg)
			fmt.Println(string(b))
		})

		if err != nil {
			fmt.Println("ERROR:", err)
			return
		}

		select {}

	case "history-dm":

		msgs, err := eng.FetchDMHistory()
		if err != nil {
			fmt.Println("ERROR:", err)
			return
		}

		for _, m := range msgs {
			b, _ := engine.MarshalDM(m)
			fmt.Println(string(b))
		}
	}
}
