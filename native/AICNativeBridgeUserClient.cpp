#include "AICNativeBridgeUserClient.h"

OSDefineMetaClassAndStructors(AICNativeBridgeUserClient, IOUserClient)

IOReturn AICNativeBridgeUserClient::externalMethod(
    uint32_t selector, IOExternalMethodArguments *arguments,
    IOExternalMethodDispatch *, OSObject *, void *) {
    // Selector 0 is a bounded, read-only ABI handshake. Nothing reaches USB.
    if (selector != 0) return kIOReturnUnsupported;
    if (!arguments || arguments->scalarInputCount != 0 ||
        arguments->structureInputSize != 0 ||
        arguments->scalarOutputCount != 1 || !arguments->scalarOutput ||
        arguments->structureOutputSize != 0) {
        return kIOReturnBadArgument;
    }
    arguments->scalarOutput[0] = 1;
    return kIOReturnSuccess;
}

IOReturn AICNativeBridgeUserClient::clientClose() {
    terminate();
    return kIOReturnSuccess;
}
