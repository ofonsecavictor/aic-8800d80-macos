#pragma once

#include <IOKit/IOCommandGate.h>
#include <IOKit/network/IOEthernetInterface.h>
#include "AICInfraInterface.h"

// BSD-side companion for an IO80211 Skywalk interface. Merely compiling this
// class does not attach or publish an interface; the controller must do that
// only after its radio bridge and native registration are ready.
class AICNativeEthernetInterface final : public IOEthernetInterface {
    OSDeclareDefaultStructors(AICNativeEthernetInterface)

public:
    bool initForAIC(IONetworkController *controller,
                    AICInfraInterface *native, IOCommandGate *gate);
    IOReturn attachToDataLinkLayer(IOOptionBits options,
                                    void *parameter) override;
    void detachFromDataLinkLayer(IOOptionBits options,
                                 void *parameter) override;
    IOService *getProvider() const override;

private:
    static IOReturn prepareBSD(OSObject *owner, void *argument,
                                void *, void *, void *);
    AICInfraInterface *nativeInterface = nullptr; // Controller owns lifetime.
    IOCommandGate *commandGate = nullptr;           // Controller owns lifetime.
    bool attached = false;
};
