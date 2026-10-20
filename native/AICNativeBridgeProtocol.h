#pragma once

#include <stdint.h>

// Shared with the future user-space AIC service. No credentials are included.
enum {
    kAICNativeBridgeVersion = 2,
    kAICNativeGetVersion = 0,
    kAICNativePublishRadioState = 1,
    kAICNativeNextCommand = 2,
    kAICNativeNextFrame = 3,
    kAICNativeSubmitFrame = 4,
    kAICNativeSetPower = 1,
    kAICNativeFrameEthernet = 1,
    kAICNativeFrameAction = 2,
    kAICNativeFrameMaxBytes = 1514,
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

// Ephemeral packet transport only. No frame is logged or written to disk.
// An action frame is a full, unprotected 802.11 management frame, not AWDL
// payload interpretation. VIF 0xff is allowed only for RX fan-out records.
typedef struct AICNativeFrame {
    uint32_t version;
    uint32_t kind;
    uint32_t sequence;
    uint32_t vif;
    uint32_t channel;
    uint32_t length;
    uint8_t data[kAICNativeFrameMaxBytes];
    uint8_t reserved[2];
} AICNativeFrame;

#if defined(__cplusplus)
static_assert(sizeof(AICNativeRadioState) == 36, "radio state ABI size");
static_assert(sizeof(AICNativeCommand) == 16, "command ABI size");
static_assert(sizeof(AICNativeFrame) == 1540, "frame ABI size");

inline bool AICNativeFrameValid(const AICNativeFrame &frame, bool fromService) {
    if (frame.version != kAICNativeBridgeVersion || !frame.sequence ||
        frame.reserved[0] || frame.reserved[1] ||
        (frame.vif > 3 && !(fromService && frame.vif == 0xff))) return false;
    if (frame.length > kAICNativeFrameMaxBytes) return false;
    for (uint32_t i = frame.length; i < kAICNativeFrameMaxBytes; ++i)
        if (frame.data[i]) return false;
    if (frame.kind == kAICNativeFrameEthernet)
        return frame.vif == 0 && frame.channel == 0 && frame.length >= 14 &&
               frame.length <= kAICNativeFrameMaxBytes;
    if (frame.kind != kAICNativeFrameAction || frame.channel < 1 ||
        frame.channel > 196 || frame.length < 25 || frame.length > 512)
        return false;
    const uint16_t control = static_cast<uint16_t>(
        uint16_t(frame.data[0]) | (uint16_t(frame.data[1]) << 8));
    if ((control & 0x00ff) != 0x00d0 || (control & 0x4000)) return false;
    if (fromService) return true; // RX may include other action categories.
    return frame.data[24] == 4 || frame.data[24] == 127;
}

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
