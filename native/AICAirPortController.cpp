// Compile-only AIC IO80211Controller ABI experiment for macOS 15.
// A disabled-match Info.plist exists; no USB ownership or installation exists.
// This file must not be loaded as a driver until the radio bridge and rollback
// path are implemented and verified in an isolated test EFI.

#include <IO80211ControllerV2.h>
#include <IOKit/IOLocks.h>
#include <mach/kmod.h>
#include "AICNativeBridgeProtocol.h"
#include "AICNativePowerMailbox.h"
#include "AICNativeFrameMailbox.h"
#include "AICNativeCapabilityBits.h"
#include "AICNativeBridgeUserClient.h"

class AICAirPortController final : public IO80211Controller {
    OSDeclareDefaultStructors(AICAirPortController)

public:
    bool init(OSDictionary *dictionary = nullptr) override;
    void free() override;
    bool start(IOService *provider) override;
    void stop(IOService *provider) override;
    bool isCommandProhibited(int command) override;
    IOReturn getHardwareAddress(IOEthernetAddress *address) override;
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
    IOReturn submitReceivedFrame(const AICNativeFrame &frame);
    IOReturn nextReceivedFrame(AICNativeFrame *frame);
    IOReturn queueTransmitFrame(const AICNativeFrame &frame);
    IOReturn nextTransmitFrame(AICNativeFrame *frame);

private:
    IOLock *stateLock = nullptr;
    AICNativeRadioState radioState = {};
    bool stateReady = false;
    AICNativePowerMailbox powerMailbox;
    AICNativeFrameMailbox receivedFrames;
    AICNativeFrameMailbox transmitFrames;
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

IOReturn AICAirPortController::getHardwareAddress(IOEthernetAddress *address) {
    static_assert(sizeof(IOEthernetAddress) == 6, "Ethernet MAC ABI size");
    if (!address || !stateLock) return kIOReturnBadArgument;
    IOLockLock(stateLock);
    if (!stateReady) {
        IOLockUnlock(stateLock);
        return kIOReturnNotReady;
    }
    bcopy(radioState.mac, address, sizeof(*address));
    IOLockUnlock(stateLock);
    return kIOReturnSuccess;
}

SInt32 AICAirPortController::handleCardSpecific(
    IO80211SkywalkInterface *, unsigned long, void *, bool) {
    return kIOReturnUnsupported;
}

IOReturn AICAirPortController::getDRIVER_VERSION(
    IO80211SkywalkInterface *, apple80211_version_data *data) {
    if (!data) return kIOReturnBadArgument;
    static const char driverVersion[] = "AIC 8800D80 native research 0.0.1";
    static_assert(sizeof(driverVersion) <= sizeof(data->string), "driver version too long");
    bzero(data, sizeof(*data));
    data->version = APPLE80211_VERSION;
    bcopy(driverVersion, data->string, sizeof(driverVersion));
    data->string_len = sizeof(driverVersion) - 1;
    return kIOReturnSuccess;
}

IOReturn AICAirPortController::getHARDWARE_VERSION(
    IO80211SkywalkInterface *, apple80211_version_data *data) {
    if (!data) return kIOReturnBadArgument;
    static const char hardwareVersion[] = "AIC 8800D80 USB; firmware not reported";
    static_assert(sizeof(hardwareVersion) <= sizeof(data->string), "hardware version too long");
    bzero(data, sizeof(*data));
    data->version = APPLE80211_VERSION;
    bcopy(hardwareVersion, data->string, sizeof(hardwareVersion));
    data->string_len = sizeof(hardwareVersion) - 1;
    return kIOReturnSuccess;
}

IOReturn AICAirPortController::getCARD_CAPABILITIES(
    IO80211SkywalkInterface *, apple80211_capability_data *data) {
    if (!data || !stateLock) return kIOReturnBadArgument;
    IOLockLock(stateLock);
    const bool available = stateReady;
    IOLockUnlock(stateLock);
    if (!available) return kIOReturnNotReady;
    bzero(data, sizeof(*data));
    data->version = APPLE80211_VERSION;
    // Only WPA2/CCMP has been exercised with this dongle. Do not advertise
    // AWDL, WPA3, monitor, WEP, or scan-completion support prematurely.
    if (!AICSetNativeCapability(data->capabilities,
                                sizeof(data->capabilities),
                                APPLE80211_CAP_AES_CCM) ||
        !AICSetNativeCapability(data->capabilities,
                                sizeof(data->capabilities),
                                APPLE80211_CAP_WPA2))
        return kIOReturnError;
    return kIOReturnSuccess;
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

IOReturn AICAirPortController::submitReceivedFrame(
    const AICNativeFrame &frame) {
    if (!stateLock || !AICNativeFrameValid(frame, true))
        return kIOReturnBadArgument;
    IOLockLock(stateLock);
    const bool queued = receivedFrames.push(frame, true);
    IOLockUnlock(stateLock);
    return queued ? kIOReturnSuccess : kIOReturnNoSpace;
}

IOReturn AICAirPortController::nextReceivedFrame(AICNativeFrame *frame) {
    if (!frame || !stateLock) return kIOReturnBadArgument;
    IOLockLock(stateLock);
    const bool available = receivedFrames.pop(frame);
    IOLockUnlock(stateLock);
    return available ? kIOReturnSuccess : kIOReturnNotReady;
}

IOReturn AICAirPortController::queueTransmitFrame(
    const AICNativeFrame &frame) {
    if (!stateLock || !AICNativeFrameValid(frame, false))
        return kIOReturnBadArgument;
    IOLockLock(stateLock);
    const bool queued = transmitFrames.push(frame, false);
    IOLockUnlock(stateLock);
    return queued ? kIOReturnSuccess : kIOReturnNoSpace;
}

IOReturn AICAirPortController::nextTransmitFrame(AICNativeFrame *frame) {
    if (!frame || !stateLock) return kIOReturnBadArgument;
    IOLockLock(stateLock);
    const bool available = transmitFrames.pop(frame);
    IOLockUnlock(stateLock);
    return available ? kIOReturnSuccess : kIOReturnNotReady;
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

extern "C" IOReturn AICNativeSubmitReceivedFrame(
    IOService *service, const AICNativeFrame *frame) {
    if (!service || !frame) return kIOReturnBadArgument;
    AICAirPortController *controller = OSDynamicCast(AICAirPortController, service);
    if (!controller) return kIOReturnBadArgument;
    return controller->submitReceivedFrame(*frame);
}

extern "C" IOReturn AICNativeNextTransmitFrame(
    IOService *service, AICNativeFrame *frame) {
    if (!service || !frame) return kIOReturnBadArgument;
    AICAirPortController *controller = OSDynamicCast(AICAirPortController, service);
    if (!controller) return kIOReturnBadArgument;
    return controller->nextTransmitFrame(frame);
}

// These are the controller-side handoff points for a future IO80211 data path.
// The current Infra interface does not call them or register with macOS.
extern "C" IOReturn AICNativeNextReceivedFrame(
    IOService *service, AICNativeFrame *frame) {
    if (!service || !frame) return kIOReturnBadArgument;
    AICAirPortController *controller = OSDynamicCast(AICAirPortController, service);
    if (!controller) return kIOReturnBadArgument;
    return controller->nextReceivedFrame(frame);
}

extern "C" IOReturn AICNativeQueueTransmitFrame(
    IOService *service, const AICNativeFrame *frame) {
    if (!service || !frame) return kIOReturnBadArgument;
    AICAirPortController *controller = OSDynamicCast(AICAirPortController, service);
    if (!controller) return kIOReturnBadArgument;
    return controller->queueTransmitFrame(*frame);
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
