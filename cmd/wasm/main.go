package main

import (
	"fmt"
	"syscall/js"

	pb "github.com/plasma/fh-mahjong/proto"
	"github.com/plasma/fh-mahjong/rules"
	"google.golang.org/protobuf/proto"
)

// The global instance of our hometown ruleset for fast local validation
var hometownRuleset = &rules.HometownRuleset{}

func main() {
	c := make(chan struct{}, 0)

	fmt.Println("Fenghua Mahjong Wasm Engine Initialized!")

	// Export an initialization function (if needed)
	js.Global().Set("mahjongInit", js.FuncOf(mahjongInit))

	// Export standard gameplay queries that the UI needs without hitting the server
	js.Global().Set("mahjongGetValidActions", js.FuncOf(mahjongGetValidActions))

	<-c
}

func mahjongInit(this js.Value, args []js.Value) interface{} {
	return "Wasm Ready"
}

// mahjongGetValidActions takes a binary byte array of a GameState and a playerSeat,
// and returns an array of valid ActionType integers.
func mahjongGetValidActions(this js.Value, args []js.Value) interface{} {
	if len(args) < 2 {
		return "error: requires GameState bytes and playerSeat"
	}

	// 1. Copy bytes from JS Uint8Array to Go []byte
	jsBytes := args[0]
	length := jsBytes.Get("length").Int()
	goBytes := make([]byte, length)
	js.CopyBytesToGo(goBytes, jsBytes)

	playerSeat := uint32(args[1].Int())

	// 2. Unmarshal the Protobuf
	var state pb.GameState
	if err := proto.Unmarshal(goBytes, &state); err != nil {
		fmt.Printf("Wasm Unmarshal Error: %v\n", err)
		return nil
	}

	// 3. Query the RuleEngine
	validActions := hometownRuleset.GetValidActions(&state, playerSeat)

	// 4. Return as JS Array
	jsArr := js.Global().Get("Array").New(len(validActions))
	for i, action := range validActions {
		jsArr.SetIndex(i, int(action))
	}

	return jsArr
}
