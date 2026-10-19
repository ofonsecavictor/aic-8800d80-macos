#pragma once

#include <stdint.h>

// Shared with the future user-space AIC service. No credentials or RF payloads.
enum {
    kAICNativeBridgeVersion = 1,
    kAICNativeGetVersion = 0,
    kAICNativePublishRadioState = 1,
};

typedef struct AICNativeRadioState {
    uint32_t version;
    uint32_t powered;
    uint32_t associated;
    uint32_t channel;
    int32_t rssi_dbm;
    uint8_t mac[6];
    uint8_t bssid[6];
    uint32_t reserved;
} AICNativeRadioState;

#if defined(__cplusplus)
static_assert(sizeof(AICNativeRadioState) == 36, "radio state ABI size");

inline bool AICNativeRadioStateValid(const AICNativeRadioState &state) {
    if (state.version != kAICNativeBridgeVersion || state.reserved != 0 ||
        state.powered > 1 || state.associated > 1 || state.channel > 196 ||
        state.rssi_dbm < -127 || state.rssi_dbm > 0) {
        return false;
    }
    if (state.associated && (!state.powered || state.channel == 0)) {
        return false;
    }
    if (!state.powered && (state.associated || state.channel != 0)) {
        return false;
    }
    return true;
}
#endif
