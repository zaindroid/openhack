/* QEMU self-test for the pqm4 module on mps3/corstone300/an547 (Cortex-M55: DSP + FPU, executes the
 * same Thumb-2 DSP/VFP code as the nRF5340's Cortex-M33F; QEMU has no M33F+DSP board model).
 * Runs keygen + sign + on-device verify and prints PK/MSG/SIG hex so the host can verify the
 * signature with an independent FIPS 204 implementation (verify.py in this directory).
 * NOT for production: randombytes() here uses the non-cryptographic test RNG.
 */
#include <zephyr/kernel.h>
#include <zephyr/random/random.h>
#include <zephyr/sys/printk.h>
#include <string.h>

#include <pqm4/mldsa44_api.h>

int randombytes(uint8_t *out, size_t n)
{
	sys_rand_get(out, n);
	return 0;
}

static uint8_t pk[CRYPTO_PUBLICKEYBYTES], sk[CRYPTO_SECRETKEYBYTES], sig[CRYPTO_BYTES];
static uint8_t msg[2048];

static void hex(const char *tag, const uint8_t *b, size_t n)
{
	printk("%s ", tag);
	for (size_t i = 0; i < n; i++) {
		printk("%02x", b[i]);
	}
	printk("\n");
}

int main(void)
{
	size_t siglen = 0, unused = 0;

	for (size_t i = 0; i < sizeof(msg); i++) {
		msg[i] = (uint8_t)(i * 7 + 3);
	}
	int rc = crypto_sign_keypair(pk, sk);

	printk("keypair rc=%d\n", rc);
	rc = crypto_sign_signature(sig, &siglen, msg, sizeof(msg), sk);
	printk("sign rc=%d siglen=%u\n", rc, (unsigned)siglen);
	rc = crypto_sign_verify(sig, siglen, msg, sizeof(msg), pk);
	printk("verify rc=%d\n", rc);
	sig[17] ^= 1;
	printk("verify_tampered rc=%d\n", crypto_sign_verify(sig, siglen, msg, sizeof(msg), pk));
	sig[17] ^= 1;
	k_thread_stack_space_get(k_current_get(), &unused);
	printk("stack_unused=%u of %u\n", (unsigned)unused, CONFIG_MAIN_STACK_SIZE);
	hex("PK", pk, sizeof(pk));
	hex("MSG", msg, sizeof(msg));
	hex("SIG", sig, siglen);
	printk("SELFTEST DONE\n");
	return 0;
}
