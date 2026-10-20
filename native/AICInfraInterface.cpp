#include "AICInfraInterface.h"
#include "AICNativeBridgeProtocol.h"
#include "AICWCLScanRequest.h"
#include "AICWCLHardwareAddress.h"
#include "AICWCLJoinRequest.h"

extern "C" IOReturn AICNativeCopyRadioState(
    IOService *service, AICNativeRadioState *state);
extern "C" IOReturn AICNativeBeginScan(
    IOService *service, const AICWCLScanRequest *request);
extern "C" IOReturn AICNativeAbortScan(IOService *service);
extern "C" IOReturn AICNativeBeginJoin(
    IOService *service, const AICWCLJoinRequest *request);
extern "C" IOReturn AICNativeAbortJoin(IOService *service);

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

IOReturn AICInfraInterface::getHardwareAddress(ether_addr *address) {
    if (!address) return kIOReturnBadArgument;
    bcopy(&stationMac, address, sizeof(stationMac));
    return kIOReturnSuccess;
}

IOReturn AICInfraInterface::setMacAddress(ether_addr &) {
    // The user-space service owns the USB radio and its firmware MAC address.
    return kIOReturnUnsupported;
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
    if (!AICDecodeWCLJoinRequest(request, kAICWCLJoinRequestSize, decoded))
        return kIOReturnUnsupported;
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
