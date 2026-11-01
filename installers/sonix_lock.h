#ifndef K2_SONIX_LOCK_H
#define K2_SONIX_LOCK_H
#include <fcntl.h>
#include <stdio.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <unistd.h>

/* Shared by the probe and installer, independent of working directory. Keep
 * the inode in place; unlinking an active lock permits competing lock files. */
static inline int k2_sonix_lock(void) {
    char path[128];
    if (snprintf(path,sizeof(path),"/tmp/k2-sonix-%lu.lock",(unsigned long)getuid()) >= (int)sizeof(path)) return -1;
    int fd=open(path,O_CREAT|O_RDWR|O_NOFOLLOW|O_CLOEXEC,0600);
    if (fd<0) return -1;
    struct stat st;
    if (fstat(fd,&st) || !S_ISREG(st.st_mode) || st.st_uid!=getuid() || st.st_nlink!=1 ||
        (st.st_mode&077) || flock(fd,LOCK_EX|LOCK_NB)) {
        close(fd);return -1;
    }
    return fd;
}
#endif
