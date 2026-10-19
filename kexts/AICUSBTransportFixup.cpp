// Uses the Lilu API and the cs_validate_page chaining approach in BlueToolFixup.
// Lilu/BlueToolFixup: Acidanthera, BSD-3-Clause; see accompanying licenses.
#include <Headers/plugin_start.hpp>
#include <Headers/kern_api.hpp>
#include <Headers/kern_version.hpp>
#include <sys/vnode.h>
#include <mach/kmod.h>

static mach_vm_address_t originalValidate = 0;
// Exact instruction sequence in the verified macOS 15.8.1 bluetoothd.
// Change only the USB recipient: interface (0x21) -> device (0x20).
static const uint8_t findRequest[] = {
    0x48,0x8d,0x75,0xb8,0x48,0xc7,0x46,0x10,0,0,0,0,0xc6,0x06,0x21
};
static const uint8_t deviceRequest[] = {
    0x48,0x8d,0x75,0xb8,0x48,0xc7,0x46,0x10,0,0,0,0,0xc6,0x06,0x20
};
// The firmware answers both LE buffer queries, but its command mask does not
// advertise V2 consistently with its feature flags. Use the verified V1 path.
static const uint8_t findBufferQuery[] = {
    0x41,0x80,0x7e,0x49,0x01,0x75,0x15,0x41,0x80,0x7e,0x27,0x10,0x73,0x1e,
    0x48,0x8d,0x35,0x6f,0x16,0,0,0xbf,0xa3,0,0,0,0xeb,0x1c
};
static const uint8_t legacyBufferQuery[] = {
    0x41,0x80,0x7e,0x49,0x01,0x75,0x15,0x41,0x80,0x7e,0x27,0x10,0x90,0x90,
    0x48,0x8d,0x35,0x6f,0x16,0,0,0xbf,0xa3,0,0,0,0xeb,0x1c
};

static void validatePage(vnode_t vp, memory_object_t pager, memory_object_offset_t offset,
                         const void *data, int *validated, int *tainted, int *nx) {
    FunctionCast(validatePage, originalValidate)(vp,pager,offset,data,validated,tainted,nx);
    char path[PATH_MAX]; int length = sizeof(path);
    if (vn_getpath(vp,path,&length) == 0 && strcmp(path,"/usr/sbin/bluetoothd") == 0) {
        if (KernelPatcher::findAndReplace(const_cast<void *>(data),PAGE_SIZE,findRequest,deviceRequest))
            IOLog("AICUSBTransportFixup: bluetoothd USB request recipient changed 21 -> 20\n");
        if (KernelPatcher::findAndReplace(const_cast<void *>(data),PAGE_SIZE,findBufferQuery,legacyBufferQuery))
            IOLog("AICUSBTransportFixup: selected verified legacy LE buffer query\n");
    }
}

static void startPlugin() {
    if (!checkKernelArgument("-aicusbfix")) {
        IOLog("AICUSBTransportFixup: disabled; requires -aicusbfix\n");
        return;
    }
    // Do not panic if registration fails. An unmodified daemon is the safe fallback.
    auto result = lilu.onPatcherLoad([](void *, KernelPatcher &patcher) {
        KernelPatcher::RouteRequest route("_cs_validate_page",validatePage,originalValidate);
        if (!patcher.routeMultipleLong(KernelPatcher::KernelID,&route,1))
            IOLog("AICUSBTransportFixup: failed to register validation hook\n");
        else
            IOLog("AICUSBTransportFixup: registered opt-in bluetoothd USB recipient fix\n");
    });
    if (result != LiluAPI::Error::NoError)
        IOLog("AICUSBTransportFixup: Lilu registration failed %u\n",static_cast<unsigned>(result));
}

PluginConfiguration ADDPR(config) {
    "AICUSBTransportFixup",parseModuleVersion("0.1.1"),LiluAPI::AllowNormal,
    nullptr,0,nullptr,0,nullptr,0,KernelVersion::Sequoia,KernelVersion::Sequoia,startPlugin
};

extern "C" {
extern kern_return_t AICUSBTransportFixup_kern_start(kmod_info_t *, void *);
extern kern_return_t AICUSBTransportFixup_kern_stop(kmod_info_t *, void *);
KMOD_EXPLICIT_DECL(local.victor.AICUSBTransportFixup,"0.1.1",AICUSBTransportFixup_kern_start,AICUSBTransportFixup_kern_stop)
__private_extern__ kmod_start_func_t *_realmain=0;
__private_extern__ kmod_stop_func_t *_antimain=0;
__private_extern__ int _kext_apple_cc=__APPLE_CC__;
}
