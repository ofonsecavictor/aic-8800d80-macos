#include <IOKit/IOService.h>
#include <IOKit/IOLib.h>
#include <IOKit/IOWorkLoop.h>
#include <IOKit/IOTimerEventSource.h>
#include <IOKit/IOBufferMemoryDescriptor.h>
#include <IOKit/usb/IOUSBHostInterface.h>
#include <IOKit/usb/IOUSBHostPipe.h>
#include <libkern/c++/OSNumber.h>
#include <libkern/c++/OSString.h>
#include <mach/kmod.h>
#include "AICProtocol.h"

class AIC88M80ModeSwitch : public IOService {
    typedef IOService super;
    OSDeclareDefaultStructors(AIC88M80ModeSwitch)
    IOUSBHostInterface *interface=nullptr;
    IOUSBHostPipe *input=nullptr, *output=nullptr;
    IOWorkLoop *loop=nullptr;
    IOTimerEventSource *timer=nullptr;
    bool opened=false;
    bool stopping=false;
    bool timerAdded=false;
    static void switchAction(OSObject *, IOTimerEventSource *);
    IOReturn command(unsigned char);
    static IOReturn shutdownAction(OSObject *, void *, void *, void *, void *);
    void closeInterface();
    void releaseResources();
public:
    IOService *probe(IOService *, SInt32 *) override;
    bool start(IOService *) override;
    void stop(IOService *) override;
    bool willTerminate(IOService *, IOOptionBits) override;
    void free() override;
    IOWorkLoop *getWorkLoop() const override { return loop; }
};
OSDefineMetaClassAndStructors(AIC88M80ModeSwitch, IOService)

static bool numberEquals(IORegistryEntry *e, const char *key, unsigned value) {
    OSNumber *n=OSDynamicCast(OSNumber,e->getProperty(key));
    return n && n->unsigned32BitValue()==value;
}
IOService *AIC88M80ModeSwitch::probe(IOService *provider, SInt32 *score) {
    IOLog("AIC88M80: 0.1.4 probe candidate\n");
    if (!super::probe(provider,score) || !OSDynamicCast(IOUSBHostInterface,provider)) return nullptr;
    OSString *name=OSDynamicCast(OSString,provider->getProperty("USB Product Name"));
    OSString *vendor=OSDynamicCast(OSString,provider->getProperty("USB Vendor Name"));
    // macOS can substitute this generic name when the product string is unavailable.
    // Keep the independently observed serial, vendor, revision and interface guards.
    OSString *serial=OSDynamicCast(OSString,provider->getProperty("USB Serial Number"));
    bool identity=name && (name->isEqualTo("88M80") ||
        (name->isEqualTo("IOUSBHostDevice") && serial && serial->isEqualTo("12345FLB6N")));
    if (!identity || !vendor || !vendor->isEqualTo("AIC") ||
        !numberEquals(provider,"idVendor",0x1111) || !numberEquals(provider,"idProduct",0x1111) ||
        !numberEquals(provider,"bcdDevice",0x1001) || !numberEquals(provider,"bConfigurationValue",1) ||
        !numberEquals(provider,"bInterfaceNumber",0) || !numberEquals(provider,"bInterfaceClass",8) ||
        !numberEquals(provider,"bInterfaceSubClass",6) || !numberEquals(provider,"bInterfaceProtocol",80)) return nullptr;
    IOLog("AIC88M80: 0.1.4 verified device and interface\n");
    return this;
}
bool AIC88M80ModeSwitch::start(IOService *provider) {
    if (!super::start(provider)) return false;
    interface=OSDynamicCast(IOUSBHostInterface,provider);
    if (!interface || !interface->open(this)) { IOLog("AIC88M80: interface open failed\n"); return false; }
    opened=true;
    const auto *config=interface->getConfigurationDescriptor();
    const auto *desc=interface->getInterfaceDescriptor();
    if (!config || !desc) {releaseResources();return false;}
    const StandardUSB::EndpointDescriptor *ep=nullptr;
    while ((ep=StandardUSB::getNextEndpointDescriptor(config,desc,ep))) {
        if ((ep->bmAttributes & 3)!=2) continue;
        if ((ep->bEndpointAddress & 0x80) && !input) input=interface->copyPipe(ep->bEndpointAddress);
        if (!(ep->bEndpointAddress & 0x80) && !output) output=interface->copyPipe(ep->bEndpointAddress);
    }
    loop=IOWorkLoop::workLoop();
    if (loop) timer=IOTimerEventSource::timerEventSource(this,switchAction);
    if (!input || !output || !loop || !timer) {releaseResources();return false;}
    if (loop->addEventSource(timer)!=kIOReturnSuccess) {releaseResources();return false;}
    timerAdded=true;
    setProperty("AICStage","storage-interface-claimed");
    IOLog("AIC88M80: claimed storage interface; scheduling mode switch\n");
    IOReturn r=timer->setTimeoutMS(300);
    if (r!=kIOReturnSuccess) {releaseResources();return false;}
    return true;
}
IOReturn AIC88M80ModeSwitch::command(unsigned char opcode) {
    IOBufferMemoryDescriptor *buf=interface->createIOBuffer(kIODirectionOutIn,31);
    if (!buf) return kIOReturnNoMemory;
    unsigned char *bytes=static_cast<unsigned char *>(buf->getBytesNoCopy());
    aicMakeCBW(bytes,opcode);
    uint32_t actual=0;
    IOReturn r=output->io(buf,31,actual,2000);
    IOLog("AIC88M80: vendor command %02x write=%08x bytes=%u\n",opcode,r,actual);
    if (r==kIOReturnSuccess && actual!=31) r=kIOReturnUnderrun;
    if (r==kIOReturnSuccess && opcode==3) {
        bzero(bytes,31);actual=0;
        r=input->io(buf,18,actual,2000);
        setProperty("AICSenseBytes",static_cast<unsigned long long>(actual),32);
        if (r==kIOReturnSuccess && actual!=18) r=kIOReturnUnderrun;
    }
    if (r==kIOReturnSuccess) {
        bzero(bytes,31); actual=0;
        r=input->io(buf,13,actual,2000);
        IOLog("AIC88M80: vendor command %02x status=%08x bytes=%u\n",opcode,r,actual);
        if (r==kIOReturnSuccess && actual==13) {
            setProperty("AICCommandStatus",static_cast<unsigned long long>(bytes[12]),32);
        }
        if (r==kIOReturnSuccess && !aicValidCSW(bytes,actual)) r=kIOReturnError;
    }
    buf->release();return r;
}
void AIC88M80ModeSwitch::switchAction(OSObject *owner,IOTimerEventSource *) {
    auto *self=OSDynamicCast(AIC88M80ModeSwitch,owner);
    if (!self || self->stopping || !self->opened) return;
    self->setProperty("AICStage","clearing-scsi-sense");
    IOReturn r=self->command(3);
    // Clear the stale ILLEGAL REQUEST status before the known-good F2 command.
    if (r==kIOReturnSuccess && !self->stopping && !self->isInactive()) {
        self->setProperty("AICStage","sending-f2");
        r=self->command(0xf2);
    }
    self->setProperty("AICLastResult",static_cast<unsigned long long>(static_cast<uint32_t>(r)),32);
    self->setProperty("AICStage",r==kIOReturnSuccess?"commands-complete-verify-usb":"command-ended-verify-log");
    // Re-enumeration, not this return code, establishes mode-switch success.
    IOLog("AIC88M80: sequence ended %08x; verify USB enumeration\n",r);
    self->closeInterface();
}
void AIC88M80ModeSwitch::closeInterface() {
    if (interface && opened) {interface->close(this);opened=false;}
}
IOReturn AIC88M80ModeSwitch::shutdownAction(OSObject *owner, void *, void *, void *, void *) {
    auto *self=OSDynamicCast(AIC88M80ModeSwitch,owner);
    if (!self) return kIOReturnBadArgument;
    self->stopping=true;
    if (self->timer) self->timer->cancelTimeout();
    self->closeInterface();
    return kIOReturnSuccess;
}
bool AIC88M80ModeSwitch::willTerminate(IOService *provider,IOOptionBits options) {
    if (loop) loop->runAction(shutdownAction,this);
    else shutdownAction(this,nullptr,nullptr,nullptr,nullptr);
    return super::willTerminate(provider,options);
}
void AIC88M80ModeSwitch::stop(IOService *provider) {
    if (loop) loop->runAction(shutdownAction,this);
    else shutdownAction(this,nullptr,nullptr,nullptr,nullptr);
    if (timerAdded) {loop->removeEventSource(timer);timerAdded=false;}
    super::stop(provider);
}
void AIC88M80ModeSwitch::releaseResources() {
    closeInterface();
    if (timerAdded) {loop->removeEventSource(timer);timerAdded=false;}
    if (timer) {timer->release();timer=nullptr;}
    if (input) {input->release();input=nullptr;}
    if (output) {output->release();output=nullptr;}
    if (loop) {loop->release();loop=nullptr;}
}
void AIC88M80ModeSwitch::free() {
    releaseResources();
    super::free();
}
extern "C" {
extern kern_return_t _start(kmod_info_t *, void *);
extern kern_return_t _stop(kmod_info_t *, void *);
KMOD_EXPLICIT_DECL(local.victor.AIC88M80ModeSwitch,"0.1.4",_start,_stop)
__private_extern__ kmod_start_func_t *_realmain=0;
__private_extern__ kmod_stop_func_t *_antimain=0;
__private_extern__ int _kext_apple_cc=__APPLE_CC__;
}
