package main

/*
#include <stdint.h>
#include <stdlib.h>

typedef struct {
	void* data;
	int len;
	char* err;
} FHBytesResult;
*/
import "C"

import (
	"errors"
	"sync"
	"unsafe"

	pb "github.com/plasma/fh-mahjong/proto"
	"github.com/plasma/fh-mahjong/rlenv"
	"google.golang.org/protobuf/proto"
)

var (
	// envMu only protects the handle table. Individual *rlenv.Env instances are
	// not safe for concurrent Reset/Step/Close calls; foreign callers must
	// serialize operations per handle.
	envMu      sync.Mutex
	nextHandle uint64 = 1
	envs              = make(map[uint64]*rlenv.Env)
)

func main() {}

//export FHEnvNew
func FHEnvNew(configPtr *C.char, configLen C.int) C.uint64_t {
	config := &pb.EnvConfig{}
	if data := inputBytes(configPtr, configLen); len(data) > 0 {
		if err := proto.Unmarshal(data, config); err != nil {
			return 0
		}
	}

	envMu.Lock()
	defer envMu.Unlock()

	handle := nextHandle
	nextHandle++
	envs[handle] = rlenv.New(config)
	return C.uint64_t(handle)
}

//export FHEnvReset
func FHEnvReset(handle C.uint64_t, requestPtr *C.char, requestLen C.int) C.FHBytesResult {
	env, err := lookupEnv(uint64(handle))
	if err != nil {
		return errorResult(err)
	}

	request := &pb.EnvResetRequest{}
	if data := inputBytes(requestPtr, requestLen); len(data) > 0 {
		if err := proto.Unmarshal(data, request); err != nil {
			return errorResult(err)
		}
	}

	response, err := env.Reset(request)
	if err != nil {
		return errorResult(err)
	}
	return marshalResult(response)
}

//export FHEnvStep
func FHEnvStep(handle C.uint64_t, requestPtr *C.char, requestLen C.int) C.FHBytesResult {
	env, err := lookupEnv(uint64(handle))
	if err != nil {
		return errorResult(err)
	}

	request := &pb.EnvStepRequest{}
	if data := inputBytes(requestPtr, requestLen); len(data) > 0 {
		if err := proto.Unmarshal(data, request); err != nil {
			return errorResult(err)
		}
	}

	response, err := env.Step(request)
	if err != nil {
		return errorResult(err)
	}
	return marshalResult(response)
}

//export FHEnvClose
func FHEnvClose(handle C.uint64_t) {
	envMu.Lock()
	defer envMu.Unlock()
	delete(envs, uint64(handle))
}

//export FHGenerateHeuristicTrajectory
func FHGenerateHeuristicTrajectory(requestPtr *C.char, requestLen C.int) C.FHBytesResult {
	request := &pb.TrajectoryRequest{}
	if data := inputBytes(requestPtr, requestLen); len(data) > 0 {
		if err := proto.Unmarshal(data, request); err != nil {
			return errorResult(err)
		}
	}

	env := rlenv.New(nil)
	response, err := env.GenerateHeuristicTrajectory(request)
	if err != nil {
		return errorResult(err)
	}
	return marshalResult(response)
}

//export FHFree
func FHFree(ptr unsafe.Pointer) {
	if ptr != nil {
		C.free(ptr)
	}
}

func lookupEnv(handle uint64) (*rlenv.Env, error) {
	envMu.Lock()
	defer envMu.Unlock()

	env, ok := envs[handle]
	if !ok {
		return nil, errors.New("invalid environment handle")
	}
	return env, nil
}

func inputBytes(ptr *C.char, length C.int) []byte {
	if ptr == nil || length <= 0 {
		return nil
	}
	return C.GoBytes(unsafe.Pointer(ptr), length)
}

func marshalResult(message proto.Message) C.FHBytesResult {
	data, err := proto.Marshal(message)
	if err != nil {
		return errorResult(err)
	}

	return C.FHBytesResult{
		data: C.CBytes(data),
		len:  C.int(len(data)),
		err:  nil,
	}
}

func errorResult(err error) C.FHBytesResult {
	return C.FHBytesResult{
		data: nil,
		len:  0,
		err:  C.CString(err.Error()),
	}
}
