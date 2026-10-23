/* AIC8800D80 FullMAC USB transport, reference radxa e9e43ed.
 * Opens only the verified Wi-Fi interface; never resets the composite device.
 */
#include <CoreFoundation/CoreFoundation.h>
#include <IOKit/IOCFPlugIn.h>
#include <IOKit/usb/IOUSBLib.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#include <time.h>
#include <CommonCrypto/CommonSymmetricKeywrap.h>
typedef struct Wifi Wifi;
typedef struct {
 Wifi *wifi;
 uint32_t length;
 uint8_t data[];
} WifiTxRequest;
struct Wifi {
 IOUSBInterfaceInterface300 **usb;
 UInt8 dataIn,dataOut,msgIn,msgOut;
 uint32_t location;
 uint64_t registryID;
 pthread_mutex_t txLock;
 pthread_cond_t txCondition;
 pthread_t txThread;
 CFRunLoopSourceRef txSource;
 CFRunLoopRef txRunLoop;
 uint64_t txSubmitted,txCompleted,txBytes,txErrors;
 uint32_t txInFlight,txHighWater,txLastError;
 int txSyncReady,txThreadStarted,txThreadReady,txStopping;
};
/* Match the reference driver's non-aggregated USB TX pool.  This remains
 * bounded (roughly 300 KiB at Ethernet MTU) while keeping the bulk OUT pipe
 * supplied across userspace/IOKit scheduling gaps. */
#define WIFI_TX_ASYNC_DEPTH 200
static int number(io_service_t s,CFStringRef k){int n=-1;CFTypeRef v=IORegistryEntryCreateCFProperty(s,k,0,0);if(v){if(CFGetTypeID(v)==CFNumberGetTypeID())CFNumberGetValue(v,kCFNumberIntType,&n);CFRelease(v);}return n;}
static int stringIs(io_service_t s,CFStringRef k,CFStringRef expected){CFTypeRef v=IORegistryEntryCreateCFProperty(s,k,0,0);int ok=v&&CFGetTypeID(v)==CFStringGetTypeID()&&CFEqual(v,expected);if(v)CFRelease(v);return ok;}
static uint32_t wifi_tx_flush(Wifi *w,uint32_t timeoutMs){
 if(!w||!w->txSyncReady)return 0;
 struct timespec deadline;clock_gettime(CLOCK_REALTIME,&deadline);
 deadline.tv_sec+=timeoutMs/1000;deadline.tv_nsec+=(long)(timeoutMs%1000)*1000000L;
 if(deadline.tv_nsec>=1000000000L){deadline.tv_sec++;deadline.tv_nsec-=1000000000L;}
 pthread_mutex_lock(&w->txLock);
 while(w->txInFlight){
  if(pthread_cond_timedwait(&w->txCondition,&w->txLock,&deadline))break;
 }
 uint32_t pending=w->txInFlight;pthread_mutex_unlock(&w->txLock);
 return pending?0xe00002d6:0;
}
static void wifi_tx_complete(void *context,IOReturn result,void *arg0){
 WifiTxRequest *request=context;Wifi *w=request->wifi;
 uint32_t actual=(uint32_t)(uintptr_t)arg0;
 pthread_mutex_lock(&w->txLock);
 if(w->txInFlight)w->txInFlight--;
 w->txCompleted++;
 if(result||actual!=request->length){
  w->txErrors++;w->txLastError=result?(uint32_t)result:0xe00002c2;
 }else w->txBytes+=actual;
 pthread_cond_broadcast(&w->txCondition);
 pthread_mutex_unlock(&w->txLock);
 free(request);
}
static void *wifi_tx_run_loop(void *context){
 Wifi *w=context;CFRunLoopRef loop=CFRunLoopGetCurrent();CFRetain(loop);
 CFRunLoopAddSource(loop,w->txSource,kCFRunLoopDefaultMode);
 pthread_mutex_lock(&w->txLock);w->txRunLoop=loop;w->txThreadReady=1;
 pthread_cond_broadcast(&w->txCondition);pthread_mutex_unlock(&w->txLock);
 for(;;){
  pthread_mutex_lock(&w->txLock);int stop=w->txStopping;pthread_mutex_unlock(&w->txLock);
  if(stop)break;
  CFRunLoopRunInMode(kCFRunLoopDefaultMode,0.25,false);
 }
 CFRunLoopRemoveSource(loop,w->txSource,kCFRunLoopDefaultMode);
 pthread_mutex_lock(&w->txLock);w->txRunLoop=NULL;pthread_mutex_unlock(&w->txLock);
 CFRelease(loop);return NULL;
}
static void wifi_start_async_tx(Wifi *w){
 if(!w||!w->usb||!w->txSyncReady)return;
 if((*w->usb)->CreateInterfaceAsyncEventSource(w->usb,&w->txSource))return;
 if(pthread_create(&w->txThread,NULL,wifi_tx_run_loop,w)){
  CFRelease(w->txSource);w->txSource=NULL;return;
 }
 w->txThreadStarted=1;
 pthread_mutex_lock(&w->txLock);
 while(!w->txThreadReady)pthread_cond_wait(&w->txCondition,&w->txLock);
 pthread_mutex_unlock(&w->txLock);
}
void wifi_close(Wifi *w){if(w){
 if(w->txSyncReady){
  if(wifi_tx_flush(w,5000)&&w->usb&&w->dataOut){
   (*w->usb)->AbortPipe(w->usb,w->dataOut);
   wifi_tx_flush(w,5000);
  }
  pthread_mutex_lock(&w->txLock);w->txStopping=1;
  CFRunLoopRef loop=w->txRunLoop;if(loop)CFRunLoopStop(loop);
  pthread_mutex_unlock(&w->txLock);
  if(w->txThreadStarted)pthread_join(w->txThread,NULL);
  if(w->txSource)CFRelease(w->txSource);
 }
 if(w->usb){(*w->usb)->USBInterfaceClose(w->usb);(*w->usb)->Release(w->usb);}
 if(w->txSyncReady){pthread_cond_destroy(&w->txCondition);pthread_mutex_destroy(&w->txLock);}
 free(w);
}}
Wifi *wifi_open(uint32_t *error){
 io_iterator_t it=0;io_service_t s;Wifi *w=NULL;*error=0xe00002c0;
 IOReturn r=IOServiceGetMatchingServices(kIOMainPortDefault,IOServiceMatching("IOUSBHostInterface"),&it);if(r){*error=r;return NULL;}
 while((s=IOIteratorNext(it))){
  int target=number(s,CFSTR("idVendor"))==0xa69c&&number(s,CFSTR("idProduct"))==0x8d81&&number(s,CFSTR("bInterfaceNumber"))==2&&number(s,CFSTR("bInterfaceClass"))==255&&stringIs(s,CFSTR("USB Serial Number"),CFSTR("20220103"))&&stringIs(s,CFSTR("USB Product Name"),CFSTR("AIC 8800D80"));
  if(!target){IOObjectRelease(s);continue;}
  uint32_t location=(uint32_t)number(s,CFSTR("locationID"));
  uint64_t registryID=0;IORegistryEntryGetRegistryEntryID(s,&registryID);
  IOCFPlugInInterface **plugin=NULL;SInt32 score=0;r=IOCreatePlugInInterfaceForService(s,kIOUSBInterfaceUserClientTypeID,kIOCFPlugInInterfaceID,&plugin,&score);IOObjectRelease(s);
  if(r||!plugin){*error=r?r:0xe00002bc;break;}
  w=calloc(1,sizeof(*w));if(!w){IODestroyPlugInInterface(plugin);*error=0xe00002bd;break;}w->location=location;w->registryID=registryID;
  if(pthread_mutex_init(&w->txLock,NULL)){IODestroyPlugInInterface(plugin);free(w);w=NULL;*error=0xe00002bd;break;}
  if(pthread_cond_init(&w->txCondition,NULL)){pthread_mutex_destroy(&w->txLock);IODestroyPlugInInterface(plugin);free(w);w=NULL;*error=0xe00002bd;break;}
  w->txSyncReady=1;
  HRESULT h=(*plugin)->QueryInterface(plugin,CFUUIDGetUUIDBytes(kIOUSBInterfaceInterfaceID300),(LPVOID*)&w->usb);IODestroyPlugInInterface(plugin);
  if(h||!w->usb){*error=(uint32_t)h;wifi_close(w);w=NULL;break;}
  r=(*w->usb)->USBInterfaceOpen(w->usb);
  if(r){*error=r;(*w->usb)->Release(w->usb);w->usb=NULL;wifi_close(w);w=NULL;break;}
  UInt8 count=0;(*w->usb)->GetNumEndpoints(w->usb,&count);
  unsigned ins=0,outs=0;
  for(UInt8 p=1;p<=count;p++){UInt8 direction,number,type,interval;UInt16 size;
   if((*w->usb)->GetPipeProperties(w->usb,p,&direction,&number,&type,&size,&interval)||type!=kUSBBulk)continue;
   if(direction==kUSBIn){if(!ins++)w->dataIn=p;else w->msgIn=p;}
   else {if(!outs++)w->dataOut=p;else w->msgOut=p;}
  }
  if(ins!=2||outs!=2||!w->msgIn||!w->msgOut){*error=0xe00002bc;wifi_close(w);w=NULL;}else {*error=0;wifi_start_async_tx(w);}
  break;
 }IOObjectRelease(it);return w;
}
uint32_t wifi_location(Wifi *w){return w?w->location:0;}
uint64_t wifi_registry_id(Wifi *w){return w?w->registryID:0;}
/* Recover only this verified dongle after a persistent boot-time interface
 * failure. Re-enumeration is equivalent to unplug/replug and is never used
 * during an open Wi-Fi session. No hub or unrelated USB device is reset. */
uint32_t wifi_reenumerate_verified(void){
 io_iterator_t it=0;io_service_t s=0,target=0;
 IOReturn r=IOServiceGetMatchingServices(kIOMainPortDefault,
     IOServiceMatching("IOUSBHostDevice"),&it);
 if(r)return r;
 while((s=IOIteratorNext(it))){
  int verified=number(s,CFSTR("idVendor"))==0xa69c&&
      number(s,CFSTR("idProduct"))==0x8d81&&
      stringIs(s,CFSTR("USB Serial Number"),CFSTR("20220103"))&&
      stringIs(s,CFSTR("USB Product Name"),CFSTR("AIC 8800D80"));
  if(verified){
   if(target){IOObjectRelease(s);IOObjectRelease(target);IOObjectRelease(it);return 0xe00002c2;}
   target=s;
  }else IOObjectRelease(s);
 }
 IOObjectRelease(it);
 if(!target)return 0xe00002c0;
 IOCFPlugInInterface **plugin=NULL;SInt32 score=0;
 r=IOCreatePlugInInterfaceForService(target,kIOUSBDeviceUserClientTypeID,
     kIOCFPlugInInterfaceID,&plugin,&score);
 IOObjectRelease(target);
 if(r||!plugin)return r?r:0xe00002bc;
 IOUSBDeviceInterface187 **device=NULL;
 HRESULT h=(*plugin)->QueryInterface(plugin,
     CFUUIDGetUUIDBytes(kIOUSBDeviceInterfaceID187),(LPVOID*)&device);
 IODestroyPlugInInterface(plugin);
 if(h||!device)return h?(uint32_t)h:0xe00002bc;
 r=(*device)->USBDeviceOpen(device);
 if(!r){
  r=(*device)->USBDeviceReEnumerate(device,0);
  (*device)->USBDeviceClose(device);
 }
 (*device)->Release(device);
 return r;
}
uint32_t wifi_validate_command_frame(const void *data,uint32_t length){
 if(!data||length<16||length>2048)return 0xe00002c2;
 const unsigned char *p=data;unsigned id=p[8]|((unsigned)p[9]<<8);
 /* Reference-derived FullMAC messages; never resets the USB device. */
 unsigned expected=0xffff;
 switch(id){case 0:case 4:expected=0;break;case 2:expected=72;break;
 case 6:expected=10;break;case 8:expected=1;break;case 14:expected=4;break;case 0x65:expected=16;break;case 0x69:expected=24;break;
 case 0x73:case 0x7b:expected=4;break;case 0x77:expected=95;break;
 case 70:expected=20;break; /* MM_REMAIN_ON_CHANNEL_REQ, research branch only. */
 case 0x1400:expected=112;break; /* ME_CONFIG_REQ: HT/VHT/HE capability ABI. */
 case 0x1402:expected=254;break; /* ME_CHAN_CONFIG_REQ: regulatory channels. */
 case 0x1411:expected=14;break; /* ME_CONFIG_MONITOR_REQ, research branch only. */
 case 0x24:expected=44;break;case 0x26:expected=1;break;case 0x1404:expected=2;break;
 case 0x1000:expected=376;break;case 0x1800:expected=320;break;case 0x1803:expected=4;break;}
 if(expected==0xffff||length!=expected+16||p[14]!=(expected&255)||p[15]!=(expected>>8))return 0xe00002c2;
 return 0;
}
uint32_t wifi_write(Wifi *w,const void *data,uint32_t length){
 if(!w)return 0xe00002c2;
 uint32_t status=wifi_validate_command_frame(data,length);
 if(status)return status;
 return (*w->usb)->WritePipeTO(w->usb,w->msgOut,(void *)data,length,1000,2000);
}
uint32_t wifi_read(Wifi *w,void *data,uint32_t *length){
 if(!w||!data||!length||*length>65536)return 0xe00002c2;
 return (*w->usb)->ReadPipeTO(w->usb,w->msgIn,data,(UInt32 *)length,1000,2000);
}
uint32_t wifi_read_data(Wifi *w,void *data,uint32_t *length){
 if(!w||!data||!length||*length>65536)return 0xe00002c2;
 return (*w->usb)->ReadPipeTO(w->usb,w->dataIn,data,(UInt32 *)length,250,500);
}
uint32_t wifi_validate_data_frame(const void *data,uint32_t length){
 if(!data||length<32||length>2048)return 0xe00002c2;
 const uint8_t *p=data;
 if((p[0]|((unsigned)p[1]<<8))!=length||p[2]!=1||p[3]!=0)return 0xe00002c2;
 unsigned payload=p[4]|((unsigned)p[5]<<8);
 if(payload>length-32||length-32-payload>3||p[28]>3)return 0xe00002c2;
 unsigned flags=p[30]|((unsigned)p[31]<<8);
 if(flags==8){
  /* Research-only 802.11 action TX: bounded, confirmed, unprotected. */
  if(payload<25||payload>512||p[26]!=3||p[27]!=255||p[29]!=255||!(p[11]&0x80))return 0xe00002c2;
  for(unsigned i=12;i<26;i++)if(p[i])return 0xe00002c2;
  unsigned fc=p[32]|((unsigned)p[33]<<8);
  if((fc&0xff)!=0xd0||(fc&0x4000))return 0xe00002c2;
  if(p[56]!=4&&p[56]!=127)return 0xe00002c2; /* No robust categories without PMF. */
 }else{
  /* Ethernet header lives in hostdesc; data area contains only payload. */
  if(flags||p[29]>31)return 0xe00002c2;
 }
 for(unsigned i=32+payload;i<length;i++)if(p[i])return 0xe00002c2;
 return 0;
}
uint32_t wifi_write_data(Wifi *w,const void *data,uint32_t length){
 if(!w)return 0xe00002c2;
 uint32_t status=wifi_validate_data_frame(data,length);
 if(status)return status;
 return (*w->usb)->WritePipeTO(w->usb,w->dataOut,(void *)data,length,1000,2000);
}
uint32_t wifi_validate_data_batch(const void *data,uint32_t length){
 if(!data||length<36||length>15364)return 0xe00002c2;
 const uint8_t *p=data;uint32_t offset=0,count=0;
 while(offset<length){
  uint32_t remaining=length-offset;
  if(remaining==4&&!p[offset]&&!p[offset+1]&&!p[offset+2]&&!p[offset+3])
   return count?0:0xe00002c2;
  if(remaining<36||count==10)return 0xe00002c2;
  uint32_t first=p[offset]|((uint32_t)p[offset+1]<<8);
  uint32_t second=p[offset+2]|((uint32_t)p[offset+3]<<8);
  if(first!=second||first>remaining-4||wifi_validate_data_frame(p+offset+4,first))
   return 0xe00002c2;
  uint32_t end=offset+4+first,aligned=(end+3)&~3U;
  if(aligned>length)return 0xe00002c2;
  for(uint32_t i=end;i<aligned;i++)if(p[i])return 0xe00002c2;
  offset=aligned;count++;
 }
 return count?0:0xe00002c2;
}
static uint32_t wifi_submit_data_async(Wifi *w,const void *data,uint32_t length){
 uint32_t status;
 if(!w->txThreadStarted)return (*w->usb)->WritePipeTO(w->usb,w->dataOut,(void *)data,length,1000,2000);
 WifiTxRequest *request=malloc(sizeof(*request)+length);if(!request)return 0xe00002bd;
 request->wifi=w;request->length=length;memcpy(request->data,data,length);
 pthread_mutex_lock(&w->txLock);
 while(w->txInFlight>=WIFI_TX_ASYNC_DEPTH&&!w->txStopping)
  pthread_cond_wait(&w->txCondition,&w->txLock);
 if(w->txStopping){pthread_mutex_unlock(&w->txLock);free(request);return 0xe00002d6;}
 w->txInFlight++;w->txSubmitted++;
 if(w->txInFlight>w->txHighWater)w->txHighWater=w->txInFlight;
 pthread_mutex_unlock(&w->txLock);
 status=(*w->usb)->WritePipeAsyncTO(w->usb,w->dataOut,request->data,length,
                                    1000,2000,wifi_tx_complete,request);
 if(status){
  pthread_mutex_lock(&w->txLock);if(w->txInFlight)w->txInFlight--;
  w->txErrors++;w->txLastError=status;pthread_cond_broadcast(&w->txCondition);
  pthread_mutex_unlock(&w->txLock);free(request);
 }
 return status;
}
uint32_t wifi_write_data_async(Wifi *w,const void *data,uint32_t length){
 if(!w)return 0xe00002c2;
 uint32_t status=wifi_validate_data_frame(data,length);if(status)return status;
 return wifi_submit_data_async(w,data,length);
}
uint32_t wifi_write_data_batch_async(Wifi *w,const void *data,uint32_t length){
 if(!w)return 0xe00002c2;
 uint32_t status=wifi_validate_data_batch(data,length);if(status)return status;
 return wifi_submit_data_async(w,data,length);
}
uint32_t wifi_tx_snapshot(Wifi *w,uint64_t *submitted,uint64_t *completed,
                          uint64_t *bytes,uint64_t *errors,uint32_t *inFlight,
                          uint32_t *highWater,uint32_t *lastError){
 if(!w||!submitted||!completed||!bytes||!errors||!inFlight||!highWater||!lastError)return 0xe00002c2;
 pthread_mutex_lock(&w->txLock);*submitted=w->txSubmitted;*completed=w->txCompleted;
 *bytes=w->txBytes;*errors=w->txErrors;*inFlight=w->txInFlight;
 *highWater=w->txHighWater;*lastError=w->txLastError;pthread_mutex_unlock(&w->txLock);
 return 0;
}
uint32_t wifi_flush_data_writes(Wifi *w,uint32_t timeoutMs){return wifi_tx_flush(w,timeoutMs);}
int wifi_unwrap(const uint8_t *key,const uint8_t *data,size_t size,uint8_t *output,size_t *outputSize){
 if(!key||!data||!output||!outputSize||size<24||size>2048||size%8)return -1;
 return CCSymmetricKeyUnwrap(kCCWRAPAES,CCrfc3394_iv,CCrfc3394_ivLen,key,16,data,size,output,outputSize);
}
