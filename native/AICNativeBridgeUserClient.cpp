#include "AICNativeBridgeUserClient.h"
#include "AICNativeBridgeProtocol.h"

// Defined by the controller. The service argument is checked before casting.
extern "C" IOReturn AICNativePublishState(IOService *service,
                                           const AICNativeRadioState *state);
extern "C" IOReturn AICNativeNextCommand(IOService *service,
                                          AICNativeCommand *command);

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
    if (selector == kAICNativeNextCommand) {
        if (arguments->scalarInputCount != 0 ||
            arguments->scalarOutputCount != 0 ||
            arguments->structureInputSize != 0 ||
            !arguments->structureOutput ||
            arguments->structureOutputSize < sizeof(AICNativeCommand)) {
            return kIOReturnBadArgument;
        }
        AICNativeCommand command = {};
        IOReturn status = AICNativeNextCommand(getService(), &command);
        if (status != kIOReturnSuccess) return status;
        if (!AICNativeCommandValid(command)) return kIOReturnError;
        bcopy(&command, arguments->structureOutput, sizeof(command));
        arguments->structureOutputSize = sizeof(command);
        return kIOReturnSuccess;
    }
    return kIOReturnUnsupported;
}

IOReturn AICNativeBridgeUserClient::clientClose() {
    terminate();
    return kIOReturnSuccess;
}
