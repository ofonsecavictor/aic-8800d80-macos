#include "AICInfraInterface.h"

OSDefineMetaClassAndStructors(AICInfraInterface, IO80211InfraInterface)

bool AICInfraInterface::initForAIC(IOService *provider, const uint8_t *mac) {
    if (!provider || !mac || (mac[0] & 1)) return false;
    bool nonzero = false;
    for (unsigned i = 0; i < sizeof(stationMac); ++i) nonzero |= mac[i] != 0;
    if (!nonzero || !IO80211InfraInterface::init()) return false;
    bcopy(mac, &stationMac, sizeof(stationMac));
    if (!IO80211SkywalkInterface::init(provider, &stationMac)) return false;
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
