/* macOS kernel-control UTUN interface. No USB or routing changes here. */
#include <sys/socket.h>
#include <sys/ioctl.h>
#include <sys/kern_control.h>
#include <sys/sys_domain.h>
#include <net/if.h>
#include <errno.h>
#include <string.h>
#include <unistd.h>

int aic_utun_open(char *name,unsigned capacity,int *error){
 if(!name||capacity<IFNAMSIZ||!error){if(error)*error=EINVAL;return -1;}
 int fd=socket(PF_SYSTEM,SOCK_DGRAM,SYSPROTO_CONTROL);
 if(fd<0){*error=errno;return -1;}
 struct ctl_info info={0};
 strlcpy(info.ctl_name,"com.apple.net.utun_control",sizeof(info.ctl_name));
 if(ioctl(fd,CTLIOCGINFO,&info)<0)goto fail;
 struct sockaddr_ctl address={0};address.sc_len=sizeof(address);
 address.sc_family=AF_SYSTEM;address.ss_sysaddr=AF_SYS_CONTROL;
 address.sc_id=info.ctl_id;address.sc_unit=0;
 if(connect(fd,(struct sockaddr *)&address,sizeof(address))<0)goto fail;
 socklen_t length=capacity;
 if(getsockopt(fd,SYSPROTO_CONTROL,2,name,&length)<0)goto fail;
 if(!memchr(name,0,capacity)){errno=EINVAL;goto fail;}
 *error=0;return fd;
fail:
 *error=errno;close(fd);return -1;
}
