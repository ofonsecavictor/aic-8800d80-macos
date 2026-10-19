#pragma once

#include <stddef.h>
#include <stdint.h>

// Observed macOS 15 WCL request layout. This is an experimental private ABI,
// not a stable Apple interface. The caller must supply the actual buffer size.
enum { kAICWCLScanRequestSize = 0x1550, kAICWCLMaxChannels = 400 };

struct AICWCLScanRequest {
    uint32_t identifier;
    uint32_t type;
    uint32_t ssidLength;
    uint8_t ssid[32];
    uint8_t bssid[6];
    uint32_t channelCount;
    uint8_t selectedChannels[32];
};

inline uint32_t AICReadLittle32(const uint8_t *data) {
    return uint32_t(data[0]) | (uint32_t(data[1]) << 8) |
           (uint32_t(data[2]) << 16) | (uint32_t(data[3]) << 24);
}

inline bool AICDecodeWCLScanRequest(const void *buffer, size_t length,
                                    AICWCLScanRequest &out) {
    if (!buffer || length < 0x58) return false;
    const uint8_t *data = static_cast<const uint8_t *>(buffer);
    const uint32_t count = AICReadLittle32(data + 0x54);
    const uint32_t ssidLength = AICReadLittle32(data + 0x1c);
    const uint32_t type = AICReadLittle32(data + 0x40);
    if (count > kAICWCLMaxChannels || ssidLength > 32 || type < 1 || type > 4 ||
        length < 0x58 + size_t(count) * 12) return false;

    AICWCLScanRequest decoded = {};
    decoded.identifier = AICReadLittle32(data);
    decoded.type = type;
    decoded.ssidLength = ssidLength;
    decoded.channelCount = count;
    for (uint32_t i = 0; i < ssidLength; ++i) decoded.ssid[i] = data[0x20 + i];
    for (unsigned i = 0; i < 6; ++i) decoded.bssid[i] = data[0x14 + i];

    for (uint32_t i = 0; i < count; ++i) {
        const uint8_t *entry = data + 0x58 + size_t(i) * 12;
        const uint32_t channel = AICReadLittle32(entry + 4);
        const uint32_t flags = AICReadLittle32(entry + 8);
        // This AIC prototype has no validated 6 GHz path. The two band flags
        // distinguish overlapping channel numbers in WCL requests.
        if (!channel || channel > 196 || (flags & 0x2000) ||
            ((flags & 0x8) && channel > 14) ||
            ((flags & 0x10) && channel <= 14)) continue;
        decoded.selectedChannels[channel / 8] |= uint8_t(1u << (channel % 8));
    }
    if (count) {
        bool anySelected = false;
        for (unsigned i = 0; i < sizeof(decoded.selectedChannels); ++i)
            anySelected |= decoded.selectedChannels[i] != 0;
        if (!anySelected) return false;
    }
    out = decoded;
    return true;
}
