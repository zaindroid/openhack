/* randombytes() for pqm4 on Zephyr, backed by the cryptographically secure RNG
 * (sys_csrand_get -> CONFIG_CSPRNG_ENABLED; on nRF5340 cpuapp the zephyr,entropy
 * source is the CryptoCell-312 TRNG).
 */
#include <zephyr/kernel.h>
#include <zephyr/random/random.h>
#include <string.h>

#include "randombytes.h"
#include <pqm4_zephyr.h>

#if !defined(CONFIG_CSPRNG_ENABLED)
#error "pqm4 randombytes() needs a CSPRNG: enable CONFIG_ENTROPY_GENERATOR with a hardware entropy driver"
#endif

static atomic_t failures;

int randombytes(uint8_t *output, size_t n)
{
	int rc = sys_csrand_get(output, n);

	if (rc != 0) {
		/* Never hand back stale buffer contents; flag the failure loudly. */
		memset(output, 0, n);
		atomic_inc(&failures);
		return -1;
	}
	return 0;
}

atomic_val_t pqm4_rng_failures(void)
{
	return atomic_get(&failures);
}
