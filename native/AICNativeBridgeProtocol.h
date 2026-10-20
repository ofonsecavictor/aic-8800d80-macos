#pragma once

#include <stdint.h>
#include "AICWCLJoinRequest.h"

// Shared with the future user-space AIC service. Ordinary state/scan messages
// contain no credentials; the separate one-shot join message contains a PMK.
enum {
    kAICNativeBridgeVersion = 2,
    kAICNativeGetVersion = 0,
    kAICNativePublishRadioState = 1,
    kAICNativeNextCommand = 2,
    kAICNativeNextFrame = 3,
    kAICNativeSubmitFrame = 4,
    kAICNativeNextScan = 5,
    kAICNativeSubmitScanResult = 6,
    kAICNativeCompleteScan = 7,
    kAICNativeEnableScanBridge = 8,
    kAICNativeNextJoin = 9,
    kAICNativeCompleteJoin = 10,
    kAICNativeNextLeave = 11,
    kAICNativeSetPower = 1,
    kAICNativeLeave = 2,
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

// Private WCL scan handoff. The service receives a bounded request and sends
// back only validated beacon metadata/IEs for the same sequence. No password
// or raw management frame is exposed by this contract.
typedef struct AICNativeScanRequest {
    uint32_t version;
    uint32_t sequence;
    uint32_t identifier;
    uint32_t type;
    uint32_t ssidLength;
    uint32_t channelCount;
    uint8_t ssid[32];
    uint8_t bssid[6];
    uint8_t reserved[2];
    uint8_t selectedChannels[32];
} AICNativeScanRequest;

typedef struct AICNativeScanResult {
    uint32_t version;
    uint32_t sequence;
    uint32_t length;
    uint8_t data[1088]; // 64-byte WCL metadata + at most 1024 IE bytes.
} AICNativeScanResult;

typedef struct AICNativeScanCompletion {
    uint32_t version;
    uint32_t sequence;
    uint32_t status;
    uint32_t reserved;
} AICNativeScanCompletion;

// One-shot PMK handoff for a WCL association request. Only the privileged
// USB-owning service may open the user client. Neither side persists this
// structure, and the kernel mailbox erases its copy when delivered/aborted.
typedef struct AICNativeJoinRequest {
    uint32_t version;
    uint32_t sequence;
    uint32_t ssidLength;
    uint32_t channelSpec;
    uint32_t rsnLength;
    uint8_t ssid[32];
    uint8_t bssid[6];
    uint8_t pmk[32];
    uint8_t rsn[257];
    uint8_t reserved;
} AICNativeJoinRequest;

typedef struct AICNativeJoinCompletion {
    uint32_t version;
    uint32_t sequence;
    uint32_t status;
    uint32_t reserved;
} AICNativeJoinCompletion;

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
static_assert(sizeof(AICNativeScanRequest) == 96, "scan request ABI size");
static_assert(sizeof(AICNativeScanResult) == 1100, "scan result ABI size");
static_assert(sizeof(AICNativeScanCompletion) == 16, "scan completion ABI size");
static_assert(sizeof(AICNativeJoinRequest) == 348, "join request ABI size");
static_assert(sizeof(AICNativeJoinCompletion) == 16, "join completion ABI size");
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
           command.sequence != 0 &&
           ((command.operation == kAICNativeSetPower && command.value <= 1) ||
            (command.operation == kAICNativeLeave && command.value == 0));
}

inline bool AICNativeScanRequestValid(const AICNativeScanRequest &request) {
    if (request.version != kAICNativeBridgeVersion || !request.sequence ||
        request.type < 1 || request.type > 4 || request.ssidLength > 32 ||
        request.channelCount > 400 || request.reserved[0] ||
        request.reserved[1]) return false;
    for (uint32_t i = request.ssidLength; i < 32; ++i)
        if (request.ssid[i]) return false;
    bool hasChannel = false;
    for (unsigned i = 0; i < 32; ++i)
        hasChannel |= request.selectedChannels[i] != 0;
    return request.channelCount == 0 ? !hasChannel : hasChannel;
}

inline bool AICNativeScanCompletionValid(
    const AICNativeScanCompletion &completion) {
    return completion.version == kAICNativeBridgeVersion &&
           completion.sequence != 0 && completion.reserved == 0;
}

inline bool AICNativeJoinRequestValid(const AICNativeJoinRequest &request) {
    const uint32_t channel = request.channelSpec & 0xff;
    if (request.version != kAICNativeBridgeVersion || !request.sequence ||
        !request.ssidLength || request.ssidLength > 32 ||
        !channel || channel > 196 ||
        request.channelSpec != (channel | (channel <= 14 ? 0x1000u : 0xd000u)) ||
        request.rsnLength > 257 || request.reserved ||
        (request.bssid[0] & 1) ||
        !AICJoinRSNSupported(request.rsn, request.rsnLength)) return false;
    bool nonzeroBssid = false;
    for (unsigned i = 0; i < 6; ++i) nonzeroBssid |= request.bssid[i] != 0;
    if (!nonzeroBssid) return false;
    for (uint32_t i = request.ssidLength; i < 32; ++i)
        if (request.ssid[i]) return false;
    for (uint32_t i = request.rsnLength; i < 257; ++i)
        if (request.rsn[i]) return false;
    return true;
}

inline bool AICNativeJoinCompletionValid(const AICNativeJoinCompletion &completion) {
    return completion.version == kAICNativeBridgeVersion &&
           completion.sequence != 0 && completion.reserved == 0;
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
