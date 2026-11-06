// Local-only UDP round trip for the experimental Windows socket bridge.
#include "../../runtime/hle/lumiose_network.c"
#include <assert.h>

int main(void) {
    Cpu c = {0};
    lumiose_socket_init(&c);
    assert(c.x[0] == 0);
    SOCKET server = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    assert(server != INVALID_SOCKET);
    DWORD timeout = 2000;
    setsockopt(server, SOL_SOCKET, SO_RCVTIMEO, (const char *)&timeout, sizeof timeout);
    struct sockaddr_in host = {0};
    host.sin_family = AF_INET;
    host.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    assert(bind(server, (struct sockaddr *)&host, sizeof host) == 0);
    int host_size = sizeof host;
    assert(getsockname(server, (struct sockaddr *)&host, &host_size) == 0);

    c.x[0] = 2; c.x[1] = 2; c.x[2] = 17;
    lumiose_socket_open(&c);
    int fd = (int)c.x[0];
    assert(fd >= 0 && fd < LUMIOSE_MAX_SOCKETS);
    uint8_t address[16] = {16, 2};
    memcpy(address + 2, &host.sin_port, 2);
    memcpy(address + 4, &host.sin_addr, 4);
    char message[] = "hello", buffer[16] = {0};
    c.x[0] = fd; c.x[1] = (uintptr_t)message; c.x[2] = 5; c.x[3] = 0;
    c.x[4] = (uintptr_t)address; c.x[5] = sizeof address;
    lumiose_socket_send(&c);
    assert(c.x[0] == 5);
    struct sockaddr_in peer;
    int peer_size = sizeof peer;
    assert(recvfrom(server, buffer, sizeof buffer, 0, (struct sockaddr *)&peer, &peer_size) == 5);
    assert(memcmp(buffer, message, 5) == 0);
    assert(sendto(server, "reply", 5, 0, (struct sockaddr *)&peer, peer_size) == 5);
    uint8_t from[16] = {0};
    uint32_t from_size = sizeof from;
    for (int i = 0; i < 100; i++) {
        c.x[0] = fd; c.x[1] = (uintptr_t)buffer; c.x[2] = sizeof buffer; c.x[3] = 0;
        c.x[4] = (uintptr_t)from; c.x[5] = (uintptr_t)&from_size;
        lumiose_socket_recv(&c);
        if (c.x[0] == 5) break;
        Sleep(10);
    }
    assert(c.x[0] == 5 && memcmp(buffer, "reply", 5) == 0);
    assert(from[0] == 16 && from[1] == 2 && from_size == 16);
    c.x[0] = fd;
    lumiose_socket_close(&c);
    assert(c.x[0] == 0);
    closesocket(server);
    lumiose_net_reset();
    return 0;
}
