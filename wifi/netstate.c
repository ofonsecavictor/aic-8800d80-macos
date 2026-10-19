/* Session-owned network state. No persistent preferences or other services. */
#include <SystemConfiguration/SystemConfiguration.h>
#include <arpa/inet.h>
#include <net/if.h>
#include <errno.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    SCDynamicStoreRef store;
    CFStringRef key4;
    CFStringRef keydns;
    CFStringRef globaldns;
} AICNetwork;

void aic_network_close(AICNetwork *network) {
    if (network) {
        /* The State keys are updated in place because configd has already
         * created placeholders for them. Remove only the entries we own when
         * the AIC session ends. */
        if (network->store) {
            if (network->globaldns) SCDynamicStoreRemoveValue(network->store,network->globaldns);
            if (network->keydns) SCDynamicStoreRemoveValue(network->store,network->keydns);
            if (network->key4) SCDynamicStoreRemoveValue(network->store,network->key4);
            CFRelease(network->store);
        }
        if (network->globaldns) CFRelease(network->globaldns);
        if (network->keydns) CFRelease(network->keydns);
        if (network->key4) CFRelease(network->key4);
        free(network);
    }
}

static void array_value(CFMutableDictionaryRef dict, CFStringRef key, CFTypeRef value) {
    CFArrayRef array=CFArrayCreate(NULL,&value,1,&kCFTypeArrayCallBacks);
    CFDictionarySetValue(dict,key,array);CFRelease(array);
}

AICNetwork *aic_network_publish(const char *name,const char *address,const char *peer,int *error) {
    struct in_addr parsed;
    if (!error) return NULL;
    *error=EINVAL;
    if (!name||strncmp(name,"utun",4)||!if_nametoindex(name)||!address||!peer||
        inet_pton(AF_INET,address,&parsed)!=1||inet_pton(AF_INET,peer,&parsed)!=1) return NULL;
    AICNetwork *network=calloc(1,sizeof(*network));
    if (!network) {*error=ENOMEM;return NULL;}
    network->store=SCDynamicStoreCreate(NULL,CFSTR("AIC88M80 Wi-Fi"),NULL,NULL);
    if (!network->store) {*error=SCError();aic_network_close(network);return NULL;}
    CFStringRef interface=CFStringCreateWithCString(NULL,name,kCFStringEncodingASCII);
    CFStringRef ip=CFStringCreateWithCString(NULL,address,kCFStringEncodingASCII);
    CFStringRef router=CFStringCreateWithCString(NULL,peer,kCFStringEncodingASCII);
    CFStringRef service=CFStringCreateWithFormat(NULL,NULL,CFSTR("AIC88M80-%@"),interface);
    network->key4=SCDynamicStoreKeyCreateNetworkServiceEntity(NULL,kSCDynamicStoreDomainState,service,kSCEntNetIPv4);
    network->keydns=SCDynamicStoreKeyCreateNetworkServiceEntity(NULL,kSCDynamicStoreDomainState,service,kSCEntNetDNS);
    /* A utun device is not a configured NetworkService, so configd does not
     * promote its service-scoped DNS entry into the resolver list.  Publish a
     * session-owned global resolver as well; AddTemporaryValue removes it when
     * this Dynamic Store session closes. */
    network->globaldns=CFStringCreateWithCString(NULL,"State:/Network/Global/DNS",kCFStringEncodingASCII);
    CFMutableDictionaryRef ipv4=CFDictionaryCreateMutable(NULL,0,&kCFTypeDictionaryKeyCallBacks,&kCFTypeDictionaryValueCallBacks);
    CFMutableDictionaryRef dns=CFDictionaryCreateMutable(NULL,0,&kCFTypeDictionaryKeyCallBacks,&kCFTypeDictionaryValueCallBacks);
    int one=1,order=100000;
    CFNumberRef primary=CFNumberCreate(NULL,kCFNumberIntType,&one);
    CFNumberRef priority=CFNumberCreate(NULL,kCFNumberIntType,&order);
    array_value(ipv4,kSCPropNetIPv4Addresses,ip);
    array_value(ipv4,kSCPropNetIPv4SubnetMasks,CFSTR("255.255.255.255"));
    CFDictionarySetValue(ipv4,kSCPropInterfaceName,interface);
    CFDictionarySetValue(ipv4,kSCPropNetIPv4Router,router);
    CFDictionarySetValue(ipv4,kSCPropNetOverridePrimary,primary);
    /* This resolver was validated directly over AIC, unlike the other
     * adapter's scoped DHCP resolver. Public IPv4 follows the AIC /1 routes. */
    array_value(dns,kSCPropNetDNSServerAddresses,CFSTR("1.1.1.1"));
    array_value(dns,kSCPropNetDNSSupplementalMatchDomains,CFSTR(""));
    array_value(dns,kSCPropNetDNSSupplementalMatchOrders,priority);
    CFDictionarySetValue(dns,kSCPropInterfaceName,interface);
    Boolean ok=SCDynamicStoreSetValue(network->store,network->key4,ipv4);
    if (ok) ok=SCDynamicStoreSetValue(network->store,network->keydns,dns);
    if (ok) ok=SCDynamicStoreSetValue(network->store,network->globaldns,dns);
    *error=ok?0:SCError();
    CFRelease(priority);CFRelease(primary);CFRelease(dns);CFRelease(ipv4);
    CFRelease(service);
    CFRelease(router);CFRelease(ip);CFRelease(interface);
    if (!ok) {aic_network_close(network);return NULL;}
    return network;
}
