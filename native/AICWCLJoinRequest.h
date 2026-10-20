#pragma once

#include <stddef.h>
#include <stdint.h>

// Observed macOS 15 WCL association layout. This private ABI has only been
// inspected offline; do not treat decoding as proof that joining works.
enum { kAICWCLJoinRequestSize = 0x2cc, kAICWCLMaxRSNLength = 257 };

struct AICWCLJoinRequest {
    uint32_t ssidLength;
    uint8_t ssid[32];
    uint8_t bssid[6];
    uint16_t channelSpec;
    uint8_t pmk[32];
    uint16_t rsnLength;
    uint8_t rsn[kAICWCLMaxRSNLength];
};

inline uint16_t AICJoinRead16(const uint8_t *p) {
    return uint16_t(p[0]) | (uint16_t(p[1]) << 8);
}

inline uint32_t AICJoinRead32(const uint8_t *p) {
    return uint32_t(AICJoinRead16(p)) | (uint32_t(AICJoinRead16(p + 2)) << 16);
}

inline bool AICJoinCCMP(const uint8_t *suite) {
    return suite[0] == 0 && suite[1] == 0x0f && suite[2] == 0xac &&
           suite[3] == 4;
}

inline bool AICJoinPSK(const uint8_t *suite) {
    return suite[0] == 0 && suite[1] == 0x0f && suite[2] == 0xac &&
           suite[3] == 2;
}

// Match the stable service's supported security: WPA2-PSK, CCMP, no required
// management-frame protection. The IE may be absent; then the selected scan
// result still needs separate validation by the future radio service.
inline bool AICJoinRSNSupported(const uint8_t *ie, size_t length) {
    if (!length) return true;
    if (!ie || length < 22 || length > kAICWCLMaxRSNLength || ie[0] != 48 ||
        size_t(ie[1]) + 2 != length || AICJoinRead16(ie + 2) != 1 ||
        !AICJoinCCMP(ie + 4)) return false;
    size_t at = 8;
    const uint16_t pairwiseCount = AICJoinRead16(ie + at);
    at += 2;
    if (!pairwiseCount || pairwiseCount > (length - at) / 4) return false;
    bool ccmp = false;
    for (uint16_t i = 0; i < pairwiseCount; ++i, at += 4)
        ccmp |= AICJoinCCMP(ie + at);
    if (!ccmp || at + 2 > length) return false;
    const uint16_t akmCount = AICJoinRead16(ie + at);
    at += 2;
    if (!akmCount || akmCount > (length - at) / 4) return false;
    bool psk = false;
    for (uint16_t i = 0; i < akmCount; ++i, at += 4)
        psk |= AICJoinPSK(ie + at);
    if (!psk) return false;
    return at + 2 > length || !(AICJoinRead16(ie + at) & (1u << 6));
}

inline bool AICDecodeWCLJoinRequest(const void *buffer, size_t length,
                                    AICWCLJoinRequest &out) {
    if (!buffer || length < kAICWCLJoinRequestSize) return false;
    const uint8_t *p = static_cast<const uint8_t *>(buffer);
    const uint32_t count = AICJoinRead32(p + 0x214);
    const uint32_t ssidLength = AICJoinRead32(p + 0x1c);
    const uint32_t keyLength = AICJoinRead32(p + 0x44);
    const uint16_t rsnLength = AICJoinRead16(p + 0xd4);
    if (!count || count > 10 || length < 0x218 + size_t(count) * 18 ||
        !ssidLength || ssidLength > 32 || keyLength != 32 ||
        rsnLength > kAICWCLMaxRSNLength ||
        AICJoinRead32(p + 0x10) != 1 || // Open-system 802.11 authentication.
        AICJoinRead32(p + 0x14) != (1u << 3) || // WPA2-PSK only.
        AICJoinRead32(p + 0x48) != 6 || // PMK, not PMKSA/WEP/PTK.
        AICJoinRead16(p + 0x4e) != 0 ||
        !AICJoinRSNSupported(p + 0xd6, rsnLength) ||
        (p[0x21c] & 1)) return false;
    bool bssidNonzero = false;
    for (unsigned i = 0; i < 6; ++i) bssidNonzero |= p[0x21c + i] != 0;
    if (!bssidNonzero) return false;
    AICWCLJoinRequest decoded = {};
    decoded.ssidLength = ssidLength;
    for (uint32_t i = 0; i < ssidLength; ++i) decoded.ssid[i] = p[0x20 + i];
    for (unsigned i = 0; i < 6; ++i) decoded.bssid[i] = p[0x21c + i];
    decoded.channelSpec = AICJoinRead16(p + 0x228);
    for (unsigned i = 0; i < 32; ++i) decoded.pmk[i] = p[0x50 + i];
    decoded.rsnLength = rsnLength;
    for (uint16_t i = 0; i < rsnLength; ++i) decoded.rsn[i] = p[0xd6 + i];
    out = decoded;
    return true;
}
