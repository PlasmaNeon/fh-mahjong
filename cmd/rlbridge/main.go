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
	"fmt"
	"math"
	"sync"
	"unsafe"

	"github.com/plasma/fh-mahjong/internal/rl"
	pb "github.com/plasma/fh-mahjong/proto"
	"google.golang.org/protobuf/proto"
)

var (
	// envMu only protects the handle table. Individual *rl.Env instances are
	// not safe for concurrent Reset/Step/Close calls; foreign callers must
	// serialize operations per handle.
	envMu      sync.Mutex
	nextHandle uint64 = 1
	envs              = make(map[uint64]*rl.Env)

	// poolMu only protects the pool handle table. Individual *rl.EnvPool
	// instances are not safe for concurrent ApplyCommands calls; foreign
	// callers must serialize operations per handle (ApplyCommands parallelizes
	// internally across slots within a single call).
	poolMu         sync.Mutex
	nextPoolHandle uint64 = 1
	pools                 = make(map[uint64]*rl.EnvPool)

	// searchPoolMu only protects the search-pool handle table. Individual
	// *rl.SearchPool instances are not safe for concurrent Step calls;
	// foreign callers must serialize operations per handle.
	searchPoolMu         sync.Mutex
	nextSearchPoolHandle uint64 = 1
	searchPools                 = make(map[uint64]*rl.SearchPool)
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
	envs[handle] = rl.New(config)
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

//export FHEnvEvaluateBranches
func FHEnvEvaluateBranches(handle C.uint64_t, requestPtr *C.char, requestLen C.int) C.FHBytesResult {
	env, err := lookupEnv(uint64(handle))
	if err != nil {
		return errorResult(err)
	}

	request := &pb.BranchEvaluationRequest{}
	if data := inputBytes(requestPtr, requestLen); len(data) > 0 {
		if err := proto.Unmarshal(data, request); err != nil {
			return errorResult(err)
		}
	}

	response, err := env.EvaluateBranches(request)
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

//export FHEnvPoolNew
func FHEnvPoolNew(requestPtr *C.char, requestLen C.int) C.uint64_t {
	request := &pb.EnvPoolNewRequest{}
	if data := inputBytes(requestPtr, requestLen); len(data) > 0 {
		if err := proto.Unmarshal(data, request); err != nil {
			return 0
		}
	}
	if request.GetSlots() == 0 {
		return 0
	}
	poolMu.Lock()
	defer poolMu.Unlock()

	handle := nextPoolHandle
	nextPoolHandle++
	pools[handle] = rl.NewEnvPool(request.GetConfig(), int(request.GetSlots()))
	return C.uint64_t(handle)
}

//export FHEnvPoolStep
func FHEnvPoolStep(handle C.uint64_t, requestPtr *C.char, requestLen C.int) C.FHBytesResult {
	poolMu.Lock()
	pool, ok := pools[uint64(handle)]
	poolMu.Unlock()
	if !ok {
		return errorResult(errors.New("invalid env pool handle"))
	}

	request := &pb.EnvPoolStepRequest{}
	if data := inputBytes(requestPtr, requestLen); len(data) > 0 {
		if err := proto.Unmarshal(data, request); err != nil {
			return errorResult(err)
		}
	}

	response, err := pool.ApplyCommands(request)
	if err != nil {
		return errorResult(err)
	}
	return marshalResult(response)
}

//export FHEnvPoolClose
func FHEnvPoolClose(handle C.uint64_t) {
	poolMu.Lock()
	defer poolMu.Unlock()
	delete(pools, uint64(handle))
}

//export FHSearchPoolNew
func FHSearchPoolNew(envHandle C.uint64_t, requestPtr *C.char, requestLen C.int) C.uint64_t {
	env, err := lookupEnv(uint64(envHandle))
	if err != nil {
		return 0
	}

	request := &pb.SearchPoolNewRequest{}
	if data := inputBytes(requestPtr, requestLen); len(data) > 0 {
		if err := proto.Unmarshal(data, request); err != nil {
			return 0
		}
	}

	// root_seat is proto3 optional: present ⇒ pin the search root explicitly
	// (duplicate-seat eval); absent ⇒ let NewSearchPool fall back to
	// currentActionSeat() (all-four-learning self-play).
	var pool *rl.SearchPool
	if request.RootSeat != nil {
		pool, err = rl.NewSearchPool(env, int(request.GetClones()), request.GetSeed(), uint64(request.GetMaxRolloutDecisions()), request.GetDeterminizations(), request.GetRootSeat())
	} else {
		pool, err = rl.NewSearchPool(env, int(request.GetClones()), request.GetSeed(), uint64(request.GetMaxRolloutDecisions()), request.GetDeterminizations())
	}
	if err != nil {
		return 0
	}

	searchPoolMu.Lock()
	defer searchPoolMu.Unlock()

	handle := nextSearchPoolHandle
	nextSearchPoolHandle++
	searchPools[handle] = pool
	return C.uint64_t(handle)
}

//export FHSearchPoolStep
func FHSearchPoolStep(handle C.uint64_t, requestPtr *C.char, requestLen C.int) C.FHBytesResult {
	searchPoolMu.Lock()
	pool, ok := searchPools[uint64(handle)]
	searchPoolMu.Unlock()
	if !ok {
		return errorResult(errors.New("invalid search pool handle"))
	}

	request := &pb.EnvPoolStepRequest{}
	if data := inputBytes(requestPtr, requestLen); len(data) > 0 {
		if err := proto.Unmarshal(data, request); err != nil {
			return errorResult(err)
		}
	}

	response, err := pool.Step(request)
	if err != nil {
		return errorResult(err)
	}
	return marshalResult(response)
}

//export FHSearchPoolClose
func FHSearchPoolClose(handle C.uint64_t) {
	searchPoolMu.Lock()
	defer searchPoolMu.Unlock()
	delete(searchPools, uint64(handle))
}

//export FHGenerateHeuristicTrajectory
func FHGenerateHeuristicTrajectory(requestPtr *C.char, requestLen C.int) C.FHBytesResult {
	request := &pb.TrajectoryRequest{}
	if data := inputBytes(requestPtr, requestLen); len(data) > 0 {
		if err := proto.Unmarshal(data, request); err != nil {
			return errorResult(err)
		}
	}

	env := rl.New(nil)
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

func lookupEnv(handle uint64) (*rl.Env, error) {
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

	// The FHBytesResult.len field is a 32-bit C int. A payload of 2 GiB or more
	// would overflow it (wrapping to a negative or truncated length), which the
	// Python side reads as an empty result, silently dropping the data. Fail
	// loudly instead so callers reduce their per-call batch/chunk size.
	if len(data) > math.MaxInt32 {
		return errorResult(fmt.Errorf(
			"bridge payload %d bytes exceeds 32-bit return limit (%d); reduce the per-call batch/chunk size",
			len(data), math.MaxInt32,
		))
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
