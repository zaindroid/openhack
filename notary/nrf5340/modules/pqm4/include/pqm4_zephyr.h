/* Zephyr glue for pqm4. */
#ifndef PQM4_ZEPHYR_H
#define PQM4_ZEPHYR_H

#include <zephyr/sys/atomic.h>

/* Number of randombytes() calls that failed since boot. pqm4 ignores the return value of
 * randombytes(), so callers compare this counter before and after an operation and discard
 * the result if it changed.
 */
atomic_val_t pqm4_rng_failures(void);

#endif
