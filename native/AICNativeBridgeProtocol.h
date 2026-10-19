#pragma once

#include <stdint.h>

// Shared with the future user-space AIC service. No credentials or RF payloads.
enum {
    kAICNativeBridgeVersion = 2,
    kAICNativeGetVersion = 0,
    kAICNativePublishRadioState = 1,
    kAICNativeNextCommand = 2,
    kAICNativeSetPower = 1,
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

typedef struct AICNativeCommand {
    uint32_t version;
    uint32_t operation;
    uint32_t sequence;
    uint32_t value;
} AICNativeCommand;

#if defined(__cplusplus)
static_assert(sizeof(AICNativeRadioState) == 36, "radio state ABI size");
static_assert(sizeof(AICNativeCommand) == 16, "command ABI size");

inline bool AICNativeCommandValid(const AICNativeCommand &command) {
    return command.version == kAICNativeBridgeVersion &&
           command.operation == kAICNativeSetPower &&
           command.sequence != 0 && command.value <= 1;
}

inline bool AICNativeRadioStateValid(const AICNativeRadioState &state) {
    if (state.version != kAICNativeBridgeVersion || state.reserved != 0 ||
        state.powered > 1 || state.associated > 1 || state.channel > 196 ||
        state.rssi_dbm < -127 || state.rssi_dbm > 0) {
        return false;
    }
    bool validMac = (state.mac[0] & 1) == 0;
    bool nonzeroMac = false, nonzeroBssid = false;
    for (unsigned i = 0; i < 6; ++i) {
        nonzeroMac |= state.mac[i] != 0;
        nonzeroBssid |= state.bssid[i] != 0;
    }
    if (!validMac || !nonzeroMac) return false;
    if (state.associated && (!state.powered || state.channel == 0 ||
                             !nonzeroBssid || (state.bssid[0] & 1))) {
        return false;
    }
    if (!state.associated && (state.channel != 0 || nonzeroBssid ||
                              state.rssi_dbm != 0)) return false;
    if (!state.powered && state.associated) {
        return false;
    }
    return true;
}
#endif
