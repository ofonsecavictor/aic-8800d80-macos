#pragma once
#include <stddef.h>
#include <stdint.h>
#include <string.h>

// Works with IOExternalMethodArguments and test descriptors. Large structure
// calls use memory descriptors; small inline calls remain supported.
template <typename Arguments>
bool AICBatchInputValid(const Arguments &args, size_t size) {
    if (args.scalarInputCount || args.scalarOutputCount ||
        args.structureOutputSize || args.structureOutputDescriptor) return false;
    if (args.structureInputDescriptor)
        return !args.structureInputSize && args.structureInputDescriptor->getLength() == size;
    return args.structureInput && args.structureInputSize == size;
}

template <typename Arguments>
bool AICBatchRead(const Arguments &args, void *buffer, size_t size) {
    if (!buffer || !size) return false;
    if (!AICBatchInputValid(args, size)) return false;
    if (args.structureInputDescriptor) {
        auto *descriptor = args.structureInputDescriptor;
        // IOUserClient supplies pageable descriptors. readBytes/writeBytes
        // require wired pages: prepare/complete must bracket every transfer.
        // Use the descriptor's existing direction, supplied by IOUserClient.
        if (descriptor->prepare() != 0) return false;
        const bool copied = descriptor->readBytes(0, buffer, size) == size;
        const bool completed = descriptor->complete() == 0;
        return copied && completed;
    }
    memcpy(buffer, args.structureInput, size);
    return true;
}

template <typename Arguments>
bool AICBatchOutputValid(const Arguments &args, size_t size) {
    if (args.scalarInputCount || args.scalarOutputCount ||
        args.structureInputSize || args.structureInputDescriptor) return false;
    if (args.structureOutputDescriptor)
        return !args.structureOutputSize && args.structureOutputDescriptor->getLength() >= size;
    return args.structureOutput && args.structureOutputSize >= size;
}

template <typename Arguments>
bool AICBatchWrite(Arguments &args, const void *buffer, size_t size) {
    if (!buffer || !size || size > UINT32_MAX) return false;
    if (!AICBatchOutputValid(args, size)) return false;
    if (args.structureOutputDescriptor) {
        auto *descriptor = args.structureOutputDescriptor;
        if (descriptor->prepare() != 0) return false;
        const bool copied = descriptor->writeBytes(0, buffer, size) == size;
        const bool completed = descriptor->complete() == 0;
        if (!copied || !completed) return false;
        args.structureOutputDescriptorSize = static_cast<uint32_t>(size);
    } else {
        memcpy(args.structureOutput, buffer, size);
        args.structureOutputSize = static_cast<uint32_t>(size);
    }
    return true;
}
