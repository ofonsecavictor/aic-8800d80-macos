#include "AICNativeBridgeUserClient.h"
#include "AICNativeBridgeProtocol.h"

// Defined by the controller. The service argument is checked before casting.
extern "C" IOReturn AICNativePublishState(IOService *service,
                                           const AICNativeRadioState *state);

OSDefineMetaClassAndStructors(AICNativeBridgeUserClient, IOUserClient)

IOReturn AICNativeBridgeUserClient::externalMethod(
    uint32_t selector, IOExternalMethodArguments *arguments,
    IOExternalMethodDispatch *, OSObject *, void *) {
    if (!arguments) return kIOReturnBadArgument;
    if (selector == kAICNativeGetVersion) {
        if (arguments->scalarInputCount != 0 ||
            arguments->structureInputSize != 0 ||
            arguments->scalarOutputCount != 1 || !arguments->scalarOutput ||
            arguments->structureOutputSize != 0) {
            return kIOReturnBadArgument;
        }
        arguments->scalarOutput[0] = kAICNativeBridgeVersion;
        return kIOReturnSuccess;
    }
    if (selector == kAICNativePublishRadioState) {
        if (arguments->scalarInputCount != 0 ||
            arguments->scalarOutputCount != 0 ||
            arguments->structureOutputSize != 0 ||
            arguments->structureInputSize != sizeof(AICNativeRadioState) ||
            !arguments->structureInput) {
            return kIOReturnBadArgument;
        }
        AICNativeRadioState state;
        bcopy(arguments->structureInput, &state, sizeof(state));
        if (!AICNativeRadioStateValid(state)) return kIOReturnBadArgument;
        return AICNativePublishState(getService(), &state);
    }
    return kIOReturnUnsupported;
}

IOReturn AICNativeBridgeUserClient::clientClose() {
    terminate();
    return kIOReturnSuccess;
}
