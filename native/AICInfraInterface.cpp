#include "AICInfraInterface.h"
#include "AICNativeBridgeProtocol.h"
#include "AICWCLScanRequest.h"
#include "AICWCLHardwareAddress.h"
#include "AICWCLJoinRequest.h"
#include "AICWCLBssCache.h"
#include "AICWCLExtendedBss.h"

namespace {
constexpr uint8_t kPassive2GHz[] = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11};
constexpr uint8_t kPassive5GHz[] = {36, 40, 44, 48};

// Sequoia's private WCL and external channel queries use different buffers.
// These layouts are checked against the pinned macOS 15 reference and expose
// only the passive channels that the user-space radio bridge actually scans.
struct __attribute__((packed)) AICWCLChannelEntry {
    uint16_t channelSpec;
    uint8_t reserved[4];
    uint8_t channel;
    uint8_t flags;
};
struct __attribute__((packed)) AICWCLChannelList {
    AICWCLChannelEntry channels[400];
    uint16_t count;
    uint8_t country[3];
    uint8_t supports6GHz;
};
static_assert(sizeof(AICWCLChannelList) == 0xc86,
              "Sequoia WCL channel list size");

struct AICNativeChannelList {
    uint8_t reserved0[8];
    uint8_t country[4];
    uint16_t count;
    uint16_t channelSpec[400];
    uint8_t channel[400];
    uint8_t indoor[400];
    uint8_t dfs[400];
    uint8_t passive[400];
    uint8_t supports40MHz[400];
    uint8_t supports80MHz[400];
    uint8_t reserved1[2];
    uint32_t firmwareChannelSpec[400];
    uint32_t channelBitmap[400];
    uint8_t reserved2[0x2720 - 0x1910];
};
static_assert(sizeof(AICNativeChannelList) == 0x2720,
              "Sequoia external channel list size");
static_assert(offsetof(AICNativeChannelList, channel) == 0x32e,
              "Sequoia external channel offset");

template <typename F> void AICForEachPassiveChannel(F append) {
    for (uint8_t channel : kPassive2GHz) append(channel, false);
    for (uint8_t channel : kPassive5GHz) append(channel, true);
}
} // namespace

extern "C" IOReturn AICNativeCopyRadioState(
    IOService *service, AICNativeRadioState *state);
extern "C" IOReturn AICNativeCopyAssociatedBss(
    IOService *service, void *reply, size_t capacity);
extern "C" IOReturn AICNativeCopyAssociatedBeacon(
    IOService *service, void *reply, size_t capacity);
extern "C" IOReturn AICNativeSetStationMac(
    IOService *service, const uint8_t mac[6]);
extern "C" IOReturn AICNativeBeginScan(
    IOService *service, const AICWCLScanRequest *request);
extern "C" IOReturn AICNativeAbortScan(IOService *service);
extern "C" IOReturn AICNativeBeginJoin(
    IOService *service, const AICWCLJoinRequest *request);
extern "C" IOReturn AICNativeAbortJoin(IOService *service);
extern "C" IOReturn AICNativeRequestLeave(IOService *service);

OSDefineMetaClassAndStructors(AICInfraInterface, IO80211InfraProtocol)

bool AICInfraInterface::initForAIC(IOService *provider, const uint8_t *mac) {
    if (!provider || !mac || (mac[0] & 1)) return false;
    bool nonzero = false;
    for (unsigned i = 0; i < sizeof(stationMac); ++i) nonzero |= mac[i] != 0;
    if (!nonzero || !IO80211InfraProtocol::init()) return false;
    bcopy(mac, &stationMac, sizeof(stationMac));
    if (!IO80211SkywalkInterface::init(provider, &stationMac)) return false;
    radioProvider = provider;
    return true;
}

IOReturn AICInfraInterface::setPowerState(unsigned long, IOService *) {
    // This Skywalk object is a virtual interface, not the AIC USB radio's
    // power driver. It has no hardware transition to await here: the radio
    // bridge handles Wi-Fi on/off requests separately. Calling the inherited
    // IO80211InfraInterface/Skywalk implementation enters its CoreCapture
    // logging path and has reproducibly panicked on macOS 15 power changes.
    return IOPMAckImplied;
}

IOReturn AICInfraInterface::getHardwareAddress(ether_addr *address) {
    if (!address) return kIOReturnBadArgument;
    bcopy(&stationMac, address, sizeof(stationMac));
    return kIOReturnSuccess;
}

IOReturn AICInfraInterface::setMacAddress(ether_addr &address) {
    if (!radioProvider) return kIOReturnNotReady;
    IOReturn status = AICNativeSetStationMac(
        radioProvider, reinterpret_cast<const uint8_t *>(&address));
    if (status == kIOReturnSuccess)
        bcopy(&address, &stationMac, sizeof(stationMac));
    return status;
}

IOReturn AICInfraInterface::getCHANNEL(apple80211_channel_data *data) {
    if (!data || !radioProvider) return kIOReturnBadArgument;
    AICNativeRadioState state = {};
    IOReturn status = AICNativeCopyRadioState(radioProvider, &state);
    if (status != kIOReturnSuccess) return status;
    if (!state.associated || !state.channel) return kIOReturnNotReady;
    bzero(data, sizeof(*data));
    data->version = APPLE80211_VERSION;
    data->channel.version = APPLE80211_VERSION;
    data->channel.channel = state.channel;
    data->channel.flags = state.channel <= 14 ? APPLE80211_C_FLAG_2GHZ
                                               : APPLE80211_C_FLAG_5GHZ;
    return kIOReturnSuccess;
}

IOReturn AICInfraInterface::getOP_MODE(apple80211_opmode_data *data) {
    if (!data) return kIOReturnBadArgument;
    bzero(data, sizeof(*data));
    data->version = APPLE80211_VERSION;
    data->op_mode = APPLE80211_M_STA;
    return kIOReturnSuccess;
}

IOReturn AICInfraInterface::getRSSI(apple80211_rssi_data *data) {
    if (!data || !radioProvider) return kIOReturnBadArgument;
    AICNativeRadioState state = {};
    const IOReturn status = AICNativeCopyRadioState(radioProvider, &state);
    if (status != kIOReturnSuccess) return status;
    if (!state.associated) return kIOReturnNotReady;
    bzero(data, sizeof(*data));
    data->version = APPLE80211_VERSION;
    data->num_radios = 1;
    data->rssi_unit = APPLE80211_UNIT_DBM;
    data->rssi[0] = state.rssi_dbm;
    data->aggregate_rssi = state.rssi_dbm;
    return kIOReturnSuccess;
}

IOReturn AICInfraInterface::getHW_ADDR(apple80211_hw_mac_address *data) {
    if (!data || !radioProvider) return kIOReturnBadArgument;
    AICNativeRadioState state = {};
    const IOReturn status = AICNativeCopyRadioState(radioProvider, &state);
    if (status != kIOReturnSuccess) return status;
    AICWCLHardwareAddress encoded = {};
    if (!AICEncodeWCLHardwareAddress(state.mac, encoded))
        return kIOReturnNotReady;
    memcpy(data, &encoded, sizeof(encoded));
    return kIOReturnSuccess;
}

IOReturn AICInfraInterface::getWCL_LOW_LATENCY_INFO(
    apple80211_low_latency_info *data) {
    if (!data) return kIOReturnBadArgument;
    // Sequoia's join manager requires this four-byte status query before it
    // will submit WCL_ASSOCIATE. No low-latency session is implemented.
    bzero(data, 4);
    return kIOReturnSuccess;
}

IOReturn AICInfraInterface::getWCL_BSS_INFO(apple80211_beacon_msg *data) {
    if (!data || !radioProvider) return kIOReturnBadArgument;
    const IOReturn status = AICNativeCopyAssociatedBss(
        radioProvider, data, AICWCLBssCache::kReplyCapacity);
    IOLog("AICNative: BSS_INFO status=%x\n", status);
    return status;
}

IOReturn AICInfraInterface::getBEACON_INFO(apple80211_beacon_info_t *data) {
    if (!data || !radioProvider) return kIOReturnBadArgument;
    const IOReturn status = AICNativeCopyAssociatedBeacon(
        radioProvider, data, AICWCLBssCache::kBeaconReplyCapacity);
    IOLog("AICNative: BEACON_INFO status=%x\n", status);
    return status;
}

IOReturn AICInfraInterface::getWCL_EXTENDED_BSS_INFO(
    apple80211_extended_bss_info *data) {
    if (!data || !radioProvider) return kIOReturnBadArgument;
    uint8_t bss[AICWCLBssCache::kReplyCapacity] = {};
    IOReturn status = AICNativeCopyAssociatedBss(
        radioProvider, bss, sizeof(bss));
    if (status != kIOReturnSuccess) {
        IOLog("AICNative: EXTENDED_BSS_INFO cache status=%x\n", status);
        return status;
    }
    AICWCLBeaconMetadata metadata = {};
    memcpy(&metadata, bss, sizeof(metadata));
    const size_t length = sizeof(metadata) + metadata.ieLength;
    const IOReturn encoded = length <= AICWCLBssCache::kPacketCapacity &&
           AICEncodeWCLExtendedBss(bss, length, data,
                                   kAICWCLExtendedBssSize)
        ? kIOReturnSuccess : kIOReturnBadArgument;
    IOLog("AICNative: EXTENDED_BSS_INFO status=%x\n", encoded);
    return encoded;
}

IOReturn AICInfraInterface::getSUPPORTED_CHANNELS(
    apple80211_sup_channel_data *data) {
    if (!data) return kIOReturnBadArgument;
    bzero(data, sizeof(*data));
    data->version = APPLE80211_VERSION;
    // Initial passive-only test plan. Do not advertise active scan, DFS,
    // 40/80 MHz, or channels whose regulatory status is unknown here.
    static const uint8_t channels24[] = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11};
    static const uint8_t channels5[] = {36, 40, 44, 48};
    for (uint8_t channel : channels24) {
        auto &item = data->supported_channels[data->num_channels++];
        item.channel = channel;
        item.flags = APPLE80211_C_FLAG_20MHZ | APPLE80211_C_FLAG_2GHZ;
    }
    for (uint8_t channel : channels5) {
        auto &item = data->supported_channels[data->num_channels++];
        item.channel = channel;
        item.flags = APPLE80211_C_FLAG_20MHZ | APPLE80211_C_FLAG_5GHZ;
    }
    return kIOReturnSuccess;
}

IOReturn AICInfraInterface::getHW_SUPPORTED_CHANNELS(
    apple80211_sup_channel_data *data) {
    return getSUPPORTED_CHANNELS(data);
}

IOReturn AICInfraInterface::getWCL_CHANNELS_INFO(
    apple80211ChannelInfo *data) {
    if (!data) return kIOReturnBadArgument;
    auto *list = reinterpret_cast<AICWCLChannelList *>(data);
    bzero(list, sizeof(*list));
    list->country[0] = 'X';
    list->country[1] = '0';
    AICForEachPassiveChannel([&](uint8_t channel, bool fiveGHz) {
        auto &entry = list->channels[list->count++];
        entry.channel = channel;
        entry.channelSpec = uint16_t(channel | (fiveGHz ? 0xd000 : 0x1000));
        entry.flags = 4; // Passive; no active-scan or DFS claim.
    });
    return kIOReturnSuccess;
}

IOReturn AICInfraInterface::getCHANNELS_INFO(
    apple80211_channels_info *data) {
    if (!data) return kIOReturnBadArgument;
    auto *list = reinterpret_cast<AICNativeChannelList *>(data);
    bzero(list, sizeof(*list));
    list->country[0] = 'X';
    list->country[1] = '0';
    AICForEachPassiveChannel([&](uint8_t channel, bool fiveGHz) {
        const unsigned index = list->count++;
        const uint16_t spec = uint16_t(channel | (fiveGHz ? 0xd000 : 0x1000));
        list->channelSpec[index] = spec;
        list->firmwareChannelSpec[index] = spec;
        list->channel[index] = channel;
        list->passive[index] = 1;
        list->channelBitmap[index] = 3U | (fiveGHz ? 4U : 0U) | 32U;
    });
    return kIOReturnSuccess;
}

IOReturn AICInfraInterface::setWCL_SCAN_REQ(apple80211ScanRequest *request) {
    AICWCLScanRequest decoded = {};
    if (!AICDecodeWCLScanRequest(request, kAICWCLScanRequestSize, decoded))
        return kIOReturnBadArgument;
    return radioProvider ? AICNativeBeginScan(radioProvider, &decoded)
                         : kIOReturnNotReady;
}

IOReturn AICInfraInterface::setWCL_SCAN_ABORT(void *) {
    return radioProvider ? AICNativeAbortScan(radioProvider)
                         : kIOReturnNotReady;
}

IOReturn AICInfraInterface::setWCL_ASSOCIATE(
    apple80211AssocCandidates *request) {
    AICWCLJoinRequest decoded = {};
    if (!AICDecodeWCLJoinRequest(request, kAICWCLJoinRequestSize, decoded)) {
        // Log only structural fields, never SSID, BSSID, PMK or RSN bytes.
        // The private WCL ABI can differ from the offline reference.
        if (request) {
            const auto *raw = reinterpret_cast<const uint8_t *>(request);
            IOLog("AICNative: WCL join rejected auth=%x security=%x ssidlen=%u "
                  "keylen=%u keytype=%u rsnlen=%u candidates=%u channel=%x\n",
                  AICJoinRead32(raw + 0x10), AICJoinRead32(raw + 0x14),
                  AICJoinRead32(raw + 0x1c), AICJoinRead32(raw + 0x44),
                  AICJoinRead32(raw + 0x48), AICJoinRead16(raw + 0xd4),
                  AICJoinRead32(raw + 0x214), AICJoinRead16(raw + 0x228));
        }
        return kIOReturnUnsupported;
    }
    const IOReturn status = radioProvider
        ? AICNativeBeginJoin(radioProvider, &decoded) : kIOReturnNotReady;
    volatile uint8_t *secret = reinterpret_cast<volatile uint8_t *>(&decoded);
    for (size_t i = 0; i < sizeof(decoded); ++i) secret[i] = 0;
    return status;
}

IOReturn AICInfraInterface::setWCL_JOIN_ABORT(void *) {
    return radioProvider ? AICNativeAbortJoin(radioProvider)
                         : kIOReturnNotReady;
}

IOReturn AICInfraInterface::setWCL_LEAVE_NETWORK(
    apple80211_leave_network *) {
    return radioProvider ? AICNativeRequestLeave(radioProvider)
                         : kIOReturnNotReady;
}

IOReturn AICInfraInterface::setWCL_LINK_STATE_UPDATE(
    apple80211_wcl_update_link_state *request) {
    if (!request || !radioProvider) return kIOReturnBadArgument;
    const uint8_t *bytes = reinterpret_cast<const uint8_t *>(request);
    if (bytes[6]) {
        AICNativeRadioState state = {};
        const IOReturn status = AICNativeCopyRadioState(radioProvider, &state);
        if (status != kIOReturnSuccess) return status;
        if (!state.associated || bcmp(state.bssid, bytes, 6) != 0)
            return kIOReturnNotReady;
        if (bytes[8])
            setCurrentApAddress(reinterpret_cast<ether_addr *>(request));
        if (bytes[7])
            setLinkState(kIO80211NetworkLinkUp, 0, false, 0);
    } else {
        setCurrentApAddress(nullptr);
        setLinkState(kIO80211NetworkLinkDown, 0, false, 0);
    }
    return kIOReturnSuccess;
}

IOReturn AICInfraInterface::setWCL_UPDATE_FAST_LANE(
    apple80211_fastlane *request) {
    if (!request) return kIOReturnBadArgument;
    const auto *bytes = reinterpret_cast<const uint8_t *>(request);
    // Match the local macOS 15 reference: acknowledge the disabled state,
    // without advertising a fast-lane feature the AIC cannot implement.
    return (bytes[0] || bytes[1]) ? kIOReturnUnsupported : kIOReturnSuccess;
}
