#include "AICInfraInterface.h"
#include "AICNativeBridgeProtocol.h"
#include "AICWCLScanRequest.h"

extern "C" IOReturn AICNativeCopyRadioState(
    IOService *service, AICNativeRadioState *state);

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

IOReturn AICInfraInterface::setWCL_SCAN_REQ(apple80211ScanRequest *request) {
    AICWCLScanRequest decoded = {};
    if (!AICDecodeWCLScanRequest(request, kAICWCLScanRequestSize, decoded))
        return kIOReturnBadArgument;
    // Do not return success until the service can execute this exact request
    // and publish result/complete messages back to macOS.
    return kIOReturnUnsupported;
}
