#pragma once

#include "AICWCLBeacon.h"

// macOS 15 WCL's 0x1e0-byte extended BSS reply. The offsets are from the
// pinned Sequoia implementation: rate set, HT MCS, VHT MCS, HE MCS, RSN IE.
// Only capabilities present in the selected, validated scan result are used.
enum { kAICWCLExtendedBssSize = 0x1e0 };

inline void AICWriteLE32(uint8_t *data, uint32_t value) {
    data[0] = uint8_t(value);
    data[1] = uint8_t(value >> 8);
    data[2] = uint8_t(value >> 16);
    data[3] = uint8_t(value >> 24);
}

inline bool AICEncodeWCLExtendedBss(const void *packet, size_t length,
                                    void *reply, size_t capacity) {
    if (!AICValidWCLBeaconPacket(packet, length) || !reply ||
        capacity < kAICWCLExtendedBssSize) return false;
    auto *out = static_cast<uint8_t *>(reply);
    memset(out, 0, kAICWCLExtendedBssSize);
    AICWriteLE32(out, 1);        // apple80211_rate_set_data.version
    AICWriteLE32(out + 0xbc, 1); // apple80211_mcs_index_set_data.version
    AICWriteLE32(out + 0xcc, 1); // VHT MCS version
    out[0xd0] = out[0xd1] = 0xff; // VHT unsupported until advertised by AP
    AICWriteLE32(out + 0xd4, 1); // HE MCS version
    out[0xd8] = out[0xd9] = 0xff;

    const auto *ies = static_cast<const uint8_t *>(packet) +
                      sizeof(AICWCLBeaconMetadata);
    const size_t iesLength = length - sizeof(AICWCLBeaconMetadata);
    unsigned rates = 0;
    bool rsnCopied = false;
    for (size_t offset = 0; offset < iesLength;) {
        const uint8_t id = ies[offset];
        const size_t size = ies[offset + 1];
        const uint8_t *body = ies + offset + 2;
        if (id == 1 || id == 50) {
            for (size_t i = 0; i < size && rates < 15; ++i) {
                const size_t entry = 8 + rates * 12;
                AICWriteLE32(out + entry, 1);
                AICWriteLE32(out + entry + 4, body[i]);
                ++rates;
            }
        } else if (id == 45 && size >= 19) {
            memcpy(out + 0xc0, body + 3, 12);
        } else if (id == 191 && size >= 10) {
            memcpy(out + 0xd0, body + 8, 2);
        } else if (id == 48 && !rsnCopied) {
            if (size + 2 > kAICWCLExtendedBssSize - 0xdd) return false;
            memcpy(out + 0xdd, ies + offset, size + 2);
            rsnCopied = true;
        }
        offset += size + 2;
    }
    out[4] = uint8_t(rates);
    return rates != 0;
}
