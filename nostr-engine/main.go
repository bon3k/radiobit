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

	if len(args) < 2 {
		fmt.Println("use: --nsec <nsec> send-public <msg> | send-dm <npub> <msg>")
		return
	}

	nsec := *nsecFlag

        if nsec == "" {
	    nsec = os.Getenv("NOSTR_NSEC")
        }

        if nsec == "" {
	    var err error
	    nsec, err = engine.LoadNsecFromFile()
	    if err != nil {
		fmt.Println("No se encontró nsec en --nsec, NOSTR_NSEC ni ~/.nostr_nsec")
		return
	    }
        }

	relays := []string{
		"wss://relay.damus.io",
		"wss://nos.lol",
                "wss://relay.snort.social",
                "wss://nostr.wine",

	}

	eng, err := engine.NewEngine(nsec, relays)
	if err != nil {
		fmt.Println("Error creando engine:", err)
		return
	}

	switch args[0] {
	case "send-public":
		ev := eng.NewEvent(1, args[1], nil)
		err := eng.PublishEvent(ev)
		if err != nil {
			fmt.Println("Error publicando evento:", err)
		}

	case "send-dm":
		eng.SendDMNIP17(args[1], args[2])
	}
}
