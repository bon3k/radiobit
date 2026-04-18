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
                fmt.Println("use: send-public <msg> | send-dm <hex> <msg> | listen-dm")
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
                        fmt.Println("No se encontró nsec")
                        return
                }
        }

        // -----------------------------
        // RELAYS
        // -----------------------------
        relays := []string{
                "wss://nos.lol",
                "wss://relay.damus.io",
        }

        eng, err := engine.NewEngine(nsec, relays)
        if err != nil {
                fmt.Println("Error creando engine:", err)
                return
        }

        // -----------------------------
        // COMMANDS
        // -----------------------------
        switch args[0] {

        case "send-public":
                if len(args) < 2 {
                        fmt.Println("use: send-public <msg>")
                        return
                }

                ev := eng.NewEvent(1, args[1], nil)
                if err := eng.PublishEvent(ev); err != nil {
                        fmt.Println("Error publicando:", err)
                }

        case "send-dm":
                if len(args) < 3 {
                        fmt.Println("use: send-dm <hex> <msg>")
                        return
                }

                if err := eng.SendDMNIP17(args[1], args[2]); err != nil {
                        fmt.Println("ERROR:", err)
                }

        case "listen-dm":

                err := eng.ListenDMNIP17(func(eventID string, sender string, msg string) {

                        fmt.Println(`{"type":"dm","id":"` + eventID + `","sender":"` + sender + `","msg":"` + msg + `"}`)
                })

                if err != nil {
                        fmt.Println("ERROR:", err)
                        return
                }

                select {}
        }
}
