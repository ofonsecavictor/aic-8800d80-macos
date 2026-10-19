// Compile-only AIC IO80211Controller ABI experiment for macOS 15.
// No Info.plist, hardware match, USB ownership, or installation is provided.
// This file must not be loaded as a driver until the radio bridge and rollback
// path are implemented and verified in an isolated test EFI.

#include <IO80211ControllerV2.h>
#include "AICNativeBridgeUserClient.h"

class AICAirPortController final : public IO80211Controller {
    OSDeclareDefaultStructors(AICAirPortController)

public:
    bool start(IOService *provider) override;
    void stop(IOService *provider) override;
    bool isCommandProhibited(int command) override;
    SInt32 handleCardSpecific(IO80211SkywalkInterface *interface,
                             unsigned long command, void *data,
                             bool isSet) override;
    IOReturn getDRIVER_VERSION(IO80211SkywalkInterface *interface,
                               apple80211_version_data *data) override;
    IOReturn getHARDWARE_VERSION(IO80211SkywalkInterface *interface,
                                 apple80211_version_data *data) override;
    IOReturn getCARD_CAPABILITIES(IO80211SkywalkInterface *interface,
                                  apple80211_capability_data *data) override;
    IOReturn getPOWER(IO80211SkywalkInterface *interface,
                      apple80211_power_data *data) override;
    IOReturn setPOWER(IO80211SkywalkInterface *interface,
                      apple80211_power_data *data) override;
    IOReturn getCOUNTRY_CODE(IO80211SkywalkInterface *interface,
                             apple80211_country_code_data *data) override;
    IOReturn setCOUNTRY_CODE(IO80211SkywalkInterface *interface,
                             apple80211_country_code_data *data) override;
    IOReturn setGET_DEBUG_INFO(IO80211SkywalkInterface *interface,
                                apple80211_debug_command *data) override;
    CCLogStream *getLogger() const override;
    CommonFaultReporter *getFaultReporterFromDriver() override;
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

bool AICAirPortController::isCommandProhibited(int) {
    return true;
}

SInt32 AICAirPortController::handleCardSpecific(
    IO80211SkywalkInterface *, unsigned long, void *, bool) {
    return kIOReturnUnsupported;
}

IOReturn AICAirPortController::getDRIVER_VERSION(
    IO80211SkywalkInterface *, apple80211_version_data *) {
    return kIOReturnUnsupported;
}

IOReturn AICAirPortController::getHARDWARE_VERSION(
    IO80211SkywalkInterface *, apple80211_version_data *) {
    return kIOReturnUnsupported;
}

IOReturn AICAirPortController::getCARD_CAPABILITIES(
    IO80211SkywalkInterface *, apple80211_capability_data *) {
    return kIOReturnUnsupported;
}

IOReturn AICAirPortController::getPOWER(
    IO80211SkywalkInterface *, apple80211_power_data *) {
    return kIOReturnUnsupported;
}

IOReturn AICAirPortController::setPOWER(
    IO80211SkywalkInterface *, apple80211_power_data *) {
    return kIOReturnUnsupported;
}

IOReturn AICAirPortController::getCOUNTRY_CODE(
    IO80211SkywalkInterface *, apple80211_country_code_data *) {
    return kIOReturnUnsupported;
}

IOReturn AICAirPortController::setCOUNTRY_CODE(
    IO80211SkywalkInterface *, apple80211_country_code_data *) {
    return kIOReturnUnsupported;
}

IOReturn AICAirPortController::setGET_DEBUG_INFO(
    IO80211SkywalkInterface *, apple80211_debug_command *) {
    return kIOReturnUnsupported;
}

CCLogStream *AICAirPortController::getLogger() const {
    return nullptr;
}

CommonFaultReporter *AICAirPortController::getFaultReporterFromDriver() {
    return nullptr;
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
