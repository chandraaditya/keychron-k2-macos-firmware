#ifndef K2_SONIX_CORE_H
#define K2_SONIX_CORE_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

enum k2_operation { K2_READ_COMMAND, K2_PROGRAM_COMMAND, K2_IMAGE_BLOCK };
typedef struct {
    void *context;
    bool (*send)(void *, enum k2_operation, const uint8_t[64]);
    bool (*receive)(void *, uint8_t[64]);
} k2_transport;
typedef struct {
    unsigned successful_image_blocks;
    bool program_enable_sent;
    bool verified;
    uint16_t initial_checksum;
    uint16_t image_checksum;
    char error[160];
} k2_result;

uint16_t k2_word_sum(const uint8_t *image, size_t length);
bool k2_run(k2_transport transport, const uint8_t *image, size_t length,
            uint16_t expected_initial_checksum, bool program, k2_result *result);
#endif
