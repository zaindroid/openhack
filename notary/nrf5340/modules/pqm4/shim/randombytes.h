/* randombytes() as declared by PQClean/mupq; implemented in zephyr/randombytes_zephyr.c. */
#ifndef PQM4_ZEPHYR_RANDOMBYTES_H
#define PQM4_ZEPHYR_RANDOMBYTES_H

#include <stddef.h>
#include <stdint.h>

int randombytes(uint8_t *output, size_t n);

#endif
