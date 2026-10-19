// Compile-only AIC IO80211Controller ABI experiment for macOS 15.
// A disabled-match Info.plist exists; no USB ownership or installation exists.
// This file must not be loaded as a driver until the radio bridge and rollback
// path are implemented and verified in an isolated test EFI.

#include <IO80211ControllerV2.h>
#include <IOKit/IOLocks.h>
#include <mach/kmod.h>
#include "AICNativeBridgeProtocol.h"
#include "AICNativePowerMailbox.h"
#include "AICNativeBridgeUserClient.h"

class AICAirPortController final : public IO80211Controller {
    OSDeclareDefaultStructors(AICAirPortController)

public:
    bool init(OSDictionary *dictionary = nullptr) override;
    void free() override;
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
    IOReturn publishRadioState(const AICNativeRadioState &state);
    IOReturn nextCommand(AICNativeCommand *command);

private:
    IOLock *stateLock = nullptr;
    AICNativeRadioState radioState = {};
    bool stateReady = false;
    AICNativePowerMailbox powerMailbox;
};

OSDefineMetaClassAndStructors(AICAirPortController, IO80211Controller)

bool AICAirPortController::init(OSDictionary *dictionary) {
    if (!IO80211Controller::init(dictionary)) return false;
    stateLock = IOLockAlloc();
    return stateLock != nullptr;
}

void AICAirPortController::free() {
    if (stateLock) {
        IOLockFree(stateLock);
        stateLock = nullptr;
    }
    IO80211Controller::free();
}

bool AICAirPortController::start(IOService *provider) {
    // This is never enabled in the packaged probe. A separate test-EFI build
    // may start the controller headlessly to validate the user-client ABI.
    // No IO80211 interface, network route, or USB claim is created here.
#if defined(AIC_HEADLESS_BRIDGE_PROBE) && AIC_HEADLESS_BRIDGE_PROBE
    if (!provider || !IO80211Controller::start(provider)) return false;
    registerService();
    return true;
#else
    // Refuse to register a ghost Wi-Fi interface without an AIC radio bridge.
    (void)provider;
    return false;
#endif
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
    IO80211SkywalkInterface *, apple80211_power_data *data) {
    if (!data || !stateLock) return kIOReturnBadArgument;
    IOLockLock(stateLock);
    if (!stateReady) {
        IOLockUnlock(stateLock);
        return kIOReturnNotReady;
    }
    const bool powered = radioState.powered != 0;
    IOLockUnlock(stateLock);
    bzero(data, sizeof(*data));
    data->version = APPLE80211_VERSION;
    data->num_radios = 1;
    data->power_state[0] = powered ? APPLE80211_POWER_ON : APPLE80211_POWER_OFF;
    return kIOReturnSuccess;
}

IOReturn AICAirPortController::publishRadioState(
    const AICNativeRadioState &state) {
    if (!stateLock || !AICNativeRadioStateValid(state)) return kIOReturnBadArgument;
    IOLockLock(stateLock);
    radioState = state;
    stateReady = true;
    powerMailbox.observe(state.powered != 0);
    IOLockUnlock(stateLock);
    return kIOReturnSuccess;
}

IOReturn AICAirPortController::nextCommand(AICNativeCommand *command) {
    if (!command || !stateLock) return kIOReturnBadArgument;
    IOLockLock(stateLock);
    if (!powerMailbox.read(command)) {
        IOLockUnlock(stateLock);
        return kIOReturnNotReady;
    }
    IOLockUnlock(stateLock);
    return kIOReturnSuccess;
}

extern "C" IOReturn AICNativePublishState(
    IOService *service, const AICNativeRadioState *state) {
    if (!service || !state) return kIOReturnBadArgument;
    AICAirPortController *controller = OSDynamicCast(AICAirPortController, service);
    if (!controller) return kIOReturnBadArgument;
    return controller->publishRadioState(*state);
}

extern "C" IOReturn AICNativeNextCommand(
    IOService *service, AICNativeCommand *command) {
    if (!service || !command) return kIOReturnBadArgument;
    AICAirPortController *controller = OSDynamicCast(AICAirPortController, service);
    if (!controller) return kIOReturnBadArgument;
    return controller->nextCommand(command);
}

IOReturn AICAirPortController::setPOWER(
    IO80211SkywalkInterface *, apple80211_power_data *data) {
    if (!data || !stateLock || data->version != APPLE80211_VERSION ||
        data->num_radios == 0 || data->power_state[0] > APPLE80211_POWER_ON) {
        return kIOReturnBadArgument;
    }
    const uint32_t requested = data->power_state[0] == APPLE80211_POWER_ON;
    IOLockLock(stateLock);
    powerMailbox.request(requested, stateReady, radioState.powered != 0);
    IOLockUnlock(stateLock);
    return kIOReturnSuccess;
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

extern "C" kern_return_t _start(kmod_info_t *, void *);
extern "C" kern_return_t _stop(kmod_info_t *, void *);
// libkmod delegates to these optional hooks; the probe has no custom hook.
extern "C" {
kmod_start_func_t *_realmain = nullptr;
kmod_stop_func_t *_antimain = nullptr;
}
KMOD_EXPLICIT_DECL(local.victor.AICNativeProbe, "0.0.1", _start, _stop)
