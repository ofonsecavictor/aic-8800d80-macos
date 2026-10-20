#include "AICNativeEthernetInterface.h"

#include <IO80211ControllerV2.h>
#include <net/if.h>

OSDefineMetaClassAndStructors(AICNativeEthernetInterface, IOEthernetInterface)

bool AICNativeEthernetInterface::initForAIC(
    IONetworkController *controller, AICInfraInterface *native,
    IOCommandGate *gate) {
    if (!controller || !native || !gate || !IOEthernetInterface::init(controller))
        return false;
    nativeInterface = native;
    commandGate = gate;
    return true;
}

IOReturn AICNativeEthernetInterface::prepareBSD(
    OSObject *, void *argument, void *, void *, void *) {
    auto *interface = static_cast<AICNativeEthernetInterface *>(argument);
    if (!interface || !interface->nativeInterface || !interface->getIfnet())
        return kIOReturnNotReady;
    auto *controller = OSDynamicCast(IO80211Controller,
                                     interface->getController());
    auto *queue = controller ? controller->getWorkQueue() : nullptr;
    if (!queue || !queue->inGate() || queue->onThread())
        return kIOReturnNotPermitted;
    return interface->nativeInterface->prepareBSDInterface(interface->getIfnet(), 0);
}

IOReturn AICNativeEthernetInterface::attachToDataLinkLayer(
    IOOptionBits options, void *parameter) {
    if (!nativeInterface || !commandGate || !setInterfaceSubType(3))
        return kIOReturnNotReady;
    IOReturn status = IOEthernetInterface::attachToDataLinkLayer(options, parameter);
    if (status != kIOReturnSuccess) return status;
    if (!getIfnet()) {
        IOEthernetInterface::detachFromDataLinkLayer(options, parameter);
        return kIOReturnNotReady;
    }
    char name[IFNAMSIZ] = {};
    snprintf(name, sizeof(name), "%s%u", ifnet_name(getIfnet()),
             ifnet_unit(getIfnet()));
    nativeInterface->setProperty("IOInterfaceName", name);
    nativeInterface->setProperty(kIOInterfaceUnit, ifnet_unit(getIfnet()), 32);
    nativeInterface->setProperty(kIOInterfaceNamePrefix, ifnet_name(getIfnet()));
    ether_addr mac = {};
    if (nativeInterface->getHardwareAddress(&mac) == kIOReturnSuccess)
        setProperty(kIOMACAddress, &mac, sizeof(mac));
    status = commandGate->runAction(prepareBSD, this);
    if (status != kIOReturnSuccess) {
        IOEthernetInterface::detachFromDataLinkLayer(options, parameter);
        return status;
    }
    attached = true;
    nativeInterface->registerService();
    return kIOReturnSuccess;
}

void AICNativeEthernetInterface::detachFromDataLinkLayer(
    IOOptionBits options, void *parameter) {
    attached = false;
    IOEthernetInterface::detachFromDataLinkLayer(options, parameter);
}

IOService *AICNativeEthernetInterface::getProvider() const {
    return attached ? nativeInterface : IOEthernetInterface::getProvider();
}
