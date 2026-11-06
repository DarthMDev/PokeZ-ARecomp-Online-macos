// Local-only UDP round trip for the Linux Lumiose socket bridge.
#include "../../runtime/hle/lumiose_network.c"
#include <assert.h>
#include <sys/time.h>

int main(void) {
    int server = socket(AF_INET, SOCK_DGRAM, 0);
    assert(server >= 0);
    struct timeval timeout = {2, 0};
    assert(!setsockopt(server, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof timeout));
    struct sockaddr_in address = {0};
    address.sin_family = AF_INET;
    address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    assert(!bind(server, (struct sockaddr *)&address, sizeof address));
    socklen_t len = sizeof address;
    assert(!getsockname(server, (struct sockaddr *)&address, &len));
    Cpu c = {0};
    c.x[0] = 2; c.x[1] = 2; c.x[2] = 17;
    lumiose_socket_open(&c);
    int fd = (int)c.x[0];
    assert(fd >= 0 && fd < LUMIOSE_MAX_SOCKETS);
    uint8_t guest_addr[16] = {16, 2};
    memcpy(guest_addr + 2, &address.sin_port, 2);
    memcpy(guest_addr + 4, &address.sin_addr, 4);
    char payload[] = "ping", response[8] = {0};
    c.x[0] = fd; c.x[1] = (uintptr_t)payload; c.x[2] = 4;
    c.x[4] = (uintptr_t)guest_addr; c.x[5] = sizeof guest_addr;
    lumiose_socket_send(&c);
    assert(c.x[0] == 4);
    struct sockaddr_in peer;
    len = sizeof peer;
    assert(recvfrom(server, response, sizeof response, 0, (struct sockaddr *)&peer, &len) == 4);
    assert(!memcmp(response, "ping", 4));
    assert(sendto(server, "pong", 4, 0, (struct sockaddr *)&peer, len) == 4);
    uint32_t addr_len = sizeof guest_addr;
    for (int tries = 0; tries < 100; tries++) {
        memset(response, 0, sizeof response);
        c.x[0] = fd; c.x[1] = (uintptr_t)response; c.x[2] = sizeof response;
        c.x[4] = (uintptr_t)guest_addr; c.x[5] = (uintptr_t)&addr_len;
        lumiose_socket_recv(&c);
        if (c.x[0] == 4) break;
        usleep(1000);
    }
    assert(c.x[0] == 4 && !memcmp(response, "pong", 4));
    c.x[0] = fd; lumiose_socket_close(&c);
    close(server);
    return 0;
}
