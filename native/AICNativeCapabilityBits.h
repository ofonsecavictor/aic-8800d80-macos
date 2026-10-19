#pragma once

#include <stddef.h>
#include <stdint.h>

inline bool AICSetNativeCapability(uint8_t *capabilities, size_t length,
                                   unsigned bit) {
    if (!capabilities || bit / 8 >= length) return false;
    capabilities[bit / 8] |= uint8_t(1u << (bit % 8));
    return true;
}
