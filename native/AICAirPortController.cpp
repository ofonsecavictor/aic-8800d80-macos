// Compile-only AIC IO80211Controller ABI experiment for macOS 15.
// No Info.plist, hardware match, USB ownership, or installation is provided.
// This file must not be loaded as a driver until the radio bridge and rollback
// path are implemented and verified in an isolated test EFI.

#include <IO80211Controller.h>
#include "AICNativeBridgeUserClient.h"

class AICAirPortController final : public IO80211Controller {
    OSDeclareDefaultStructors(AICAirPortController)

public:
    bool start(IOService *provider) override;
    void stop(IOService *provider) override;
    SInt32 apple80211Request(unsigned int requestType, int requestNumber,
                            IO80211Interface *interface, void *data) override;
    SInt32 stopDMA() override;
    UInt32 hardwareOutputQueueDepth(IO80211Interface *interface) override;
    SInt32 performCountryCodeOperation(IO80211Interface *interface,
                                      IO80211CountryCodeOp operation) override;
    SInt32 enableFeature(IO80211FeatureCode code, void *data) override;
    IOReturn newUserClient(task_t owningTask, void *securityID, UInt32 type,
                           OSDictionary *properties,
                           IOUserClient **handler) override;
};

OSDefineMetaClassAndStructors(AICAirPortController, IO80211Controller)

bool AICAirPortController::start(IOService *provider) {
    // Refuse to register a ghost Wi-Fi interface without an AIC radio bridge.
    (void)provider;
    return false;
}

void AICAirPortController::stop(IOService *provider) {
    IO80211Controller::stop(provider);
}

SInt32 AICAirPortController::apple80211Request(unsigned int, int,
                                               IO80211Interface *, void *) {
    return kIOReturnUnsupported;
}

SInt32 AICAirPortController::stopDMA() {
    return kIOReturnSuccess;
}

UInt32 AICAirPortController::hardwareOutputQueueDepth(IO80211Interface *) {
    return 0;
}

SInt32 AICAirPortController::performCountryCodeOperation(
    IO80211Interface *, IO80211CountryCodeOp) {
    return kIOReturnUnsupported;
}

SInt32 AICAirPortController::enableFeature(IO80211FeatureCode, void *) {
    return kIOReturnUnsupported;
}

IOReturn AICAirPortController::newUserClient(
    task_t owningTask, void *securityID, UInt32 type,
    OSDictionary *properties, IOUserClient **handler) {
    if (!handler || type != 0) return kIOReturnBadArgument;
    *handler = nullptr;
    if (IOUserClient::clientHasPrivilege(
            securityID, kIOClientPrivilegeAdministrator) != kIOReturnSuccess) {
        return kIOReturnNotPrivileged;
    }

    AICNativeBridgeUserClient *client = OSTypeAlloc(AICNativeBridgeUserClient);
    if (!client) return kIOReturnNoMemory;
    if (!client->initWithTask(owningTask, securityID, type, properties)) {
        client->release();
        return kIOReturnError;
    }
    if (!client->attach(this)) {
        client->release();
        return kIOReturnError;
    }
    if (!client->start(this)) {
        client->detach(this);
        client->release();
        return kIOReturnError;
    }
    *handler = client;
    return kIOReturnSuccess;
}
