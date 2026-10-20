/* Mosca Notary: ML-DSA-44 signer on the nRF5340 application core.
 *
 * Transport: UART0, which the DK's on-board J-Link exposes as a virtual COM port (115200 8N1).
 * Line protocol, exactly one reply line per command line:
 *   PUB            -> PUB <pk hex, 1312 bytes>
 *   SIGN <hex>     -> SIG <sig hex, 2420 bytes>        (message up to 2048 bytes)
 *   GEN            -> OK keygen <n> ms                  (refused if a key already exists)
 *   GEN FORCE      -> OK keygen <n> ms                  (replaces the stored key)
 *   TIME           -> TIME keygen_ms=<n> sign_ms=<n> sign_bytes=<n> [extra key=value fields]
 *   anything else  -> ERR <reason>
 * Nothing else is ever written to the UART: console, printk, logging and the boot banner are disabled.
 *
 * Crypto: pqm4 ML-DSA-44 (FIPS 204, pure, empty context) via the modules/pqm4 Zephyr module.
 * The key pair is stored as one settings entry (pk || sk) in NVS so it is written atomically.
 */
#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/settings/settings.h>
#include <zephyr/sys/ring_buffer.h>
#include <zephyr/sys/util.h>
#include <cmsis_core.h>
#include <nrfx_clock.h>
#include <string.h>
#include <stdio.h>

#include <pqm4/mldsa44_api.h> /* crypto_sign_keypair / crypto_sign_signature, CRYPTO_* sizes */
#include <pqm4_zephyr.h>      /* pqm4_rng_failures() */

#define MSG_MAX  2048
#define LINE_MAX (5 + 2 * MSG_MAX + 16) /* "SIGN " + hex + slack */
#define RX_RING  8192

BUILD_ASSERT(CRYPTO_PUBLICKEYBYTES == 1312 && CRYPTO_SECRETKEYBYTES == 2560 && CRYPTO_BYTES == 2420,
	     "unexpected ML-DSA-44 parameter sizes");
#if defined(CONFIG_PQM4_MLDSA44_M4F)
/* pqm4 benchmarks: m4f needs ~45 KB of stack for signing (38 KB for keygen). */
BUILD_ASSERT(CONFIG_MAIN_STACK_SIZE >= 52 * 1024, "m4f ML-DSA-44 needs >= 52 KB main stack");
#endif

static const struct device *const uart = DEVICE_DT_GET(DT_NODELABEL(uart0));

static uint8_t keypair[CRYPTO_PUBLICKEYBYTES + CRYPTO_SECRETKEYBYTES]; /* pk || sk */
static uint8_t *const pk = keypair;
static uint8_t *const sk = keypair + CRYPTO_PUBLICKEYBYTES;
static uint8_t sig[CRYPTO_BYTES];
static uint8_t msg[MSG_MAX];
static char line[LINE_MAX];
static bool have_key;
static int storage_rc = -EAGAIN;

/* Measurements of the last GEN / SIGN, reported by TIME. */
static struct {
	uint32_t keygen_us, keygen_cycles;
	uint32_t sign_us, sign_cycles, sign_bytes;
} last;

/* ---------------------------------------------------------------- settings */

static int notary_set(const char *name, size_t len, settings_read_cb read_cb, void *cb_arg)
{
	const char *next;

	if (settings_name_steq(name, "key", &next) && !next) {
		if (len != sizeof(keypair)) {
			return -EINVAL; /* stale/foreign entry: ignore, device stays unprovisioned */
		}
		ssize_t rc = read_cb(cb_arg, keypair, sizeof(keypair));

		if (rc != (ssize_t)sizeof(keypair)) {
			memset(keypair, 0, sizeof(keypair));
			return rc < 0 ? (int)rc : -EIO;
		}
		have_key = true;
		return 0;
	}
	return -ENOENT;
}
SETTINGS_STATIC_HANDLER_DEFINE(notary, "notary", NULL, notary_set, NULL, NULL);

/* ---------------------------------------------------------------- uart */

RING_BUF_DECLARE(rx_ring, RX_RING);
static K_SEM_DEFINE(rx_sem, 0, 1);
static atomic_t rx_overrun;

static void uart_isr(const struct device *dev, void *user_data)
{
	ARG_UNUSED(user_data);

	while (uart_irq_update(dev) && uart_irq_rx_ready(dev)) {
		uint8_t *p;
		uint32_t space = ring_buf_put_claim(&rx_ring, &p, RX_RING);

		if (space == 0) {
			uint8_t junk[32];

			(void)uart_fifo_read(dev, junk, sizeof(junk));
			atomic_set(&rx_overrun, 1);
			continue;
		}
		int n = uart_fifo_read(dev, p, space);

		ring_buf_put_finish(&rx_ring, n > 0 ? n : 0);
		if (n <= 0) {
			break;
		}
	}
	k_sem_give(&rx_sem);
}

static void put(const char *s)
{
	while (*s) {
		uart_poll_out(uart, *s++);
	}
}

static void put_hex(const uint8_t *b, size_t n)
{
	static const char h[] = "0123456789abcdef";

	for (size_t i = 0; i < n; i++) {
		uart_poll_out(uart, h[b[i] >> 4]);
		uart_poll_out(uart, h[b[i] & 15]);
	}
}

/* ---------------------------------------------------------------- helpers */

static int nibble(char c)
{
	if (c >= '0' && c <= '9') {
		return c - '0';
	}
	if (c >= 'a' && c <= 'f') {
		return c - 'a' + 10;
	}
	if (c >= 'A' && c <= 'F') {
		return c - 'A' + 10;
	}
	return -1;
}

/* Strict hex decoder: even length, hex digits only, at most `max` bytes. */
static int unhex(const char *s, uint8_t *out, size_t max)
{
	size_t len = strlen(s);

	if (len % 2 || len / 2 > max) {
		return -1;
	}
	for (size_t i = 0; i < len / 2; i++) {
		int hi = nibble(s[2 * i]), lo = nibble(s[2 * i + 1]);

		if (hi < 0 || lo < 0) {
			return -1;
		}
		out[i] = (uint8_t)((hi << 4) | lo);
	}
	return (int)(len / 2);
}

static void cycles_start(void)
{
#if defined(DCB)
	DCB->DEMCR |= DCB_DEMCR_TRCENA_Msk;
#else
	CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
#endif
	DWT->CYCCNT = 0;
	DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
}

static uint32_t ticks_to_us(int64_t ticks)
{
	return (uint32_t)k_ticks_to_us_floor64((uint64_t)ticks);
}

static size_t main_stack_unused(void)
{
	size_t unused = 0;

	(void)k_thread_stack_space_get(k_current_get(), &unused);
	return unused;
}

/* ---------------------------------------------------------------- commands */

static void cmd_gen(void)
{
	uint8_t new_pair[sizeof(keypair)];
	char b[64];

	if (storage_rc) {
		snprintf(b, sizeof(b), "ERR storage %d\n", storage_rc);
		put(b);
		return;
	}
	atomic_val_t rng_before = pqm4_rng_failures();
	int64_t t0 = k_uptime_ticks();

	cycles_start();
	int rc = crypto_sign_keypair(new_pair, new_pair + CRYPTO_PUBLICKEYBYTES);
	uint32_t cyc = DWT->CYCCNT;
	int64_t t1 = k_uptime_ticks();

	if (pqm4_rng_failures() != rng_before) {
		memset(new_pair, 0, sizeof(new_pair));
		put("ERR entropy\n");
		return;
	}
	if (rc) {
		memset(new_pair, 0, sizeof(new_pair));
		snprintf(b, sizeof(b), "ERR keygen %d\n", rc);
		put(b);
		return;
	}
	rc = settings_save_one("notary/key", new_pair, sizeof(new_pair));
	if (rc) {
		memset(new_pair, 0, sizeof(new_pair));
		snprintf(b, sizeof(b), "ERR save %d\n", rc);
		put(b);
		return;
	}
	memcpy(keypair, new_pair, sizeof(keypair));
	memset(new_pair, 0, sizeof(new_pair));
	have_key = true;
	last.keygen_us = ticks_to_us(t1 - t0);
	last.keygen_cycles = cyc;
	snprintf(b, sizeof(b), "OK keygen %u ms\n", (unsigned)(last.keygen_us / 1000));
	put(b);
}

static void cmd_sign(const char *hex)
{
	if (!have_key) {
		put("ERR no key; send GEN\n");
		return;
	}
	int n = unhex(hex, msg, sizeof(msg));

	if (n < 0) {
		put("ERR hex\n");
		return;
	}
	size_t siglen = 0;
	atomic_val_t rng_before = pqm4_rng_failures();
	int64_t t0 = k_uptime_ticks();

	cycles_start();
	int rc = crypto_sign_signature(sig, &siglen, msg, (size_t)n, sk);
	uint32_t cyc = DWT->CYCCNT;
	int64_t t1 = k_uptime_ticks();

	if (pqm4_rng_failures() != rng_before) {
		put("ERR entropy\n");
		return;
	}
	if (rc || siglen != CRYPTO_BYTES) {
		put("ERR sign\n");
		return;
	}
	last.sign_us = ticks_to_us(t1 - t0);
	last.sign_cycles = cyc;
	last.sign_bytes = (uint32_t)n;
	put("SIG ");
	put_hex(sig, siglen);
	put("\n");
}

static void cmd_time(void)
{
	char b[256];

	snprintf(b, sizeof(b),
		 "TIME keygen_ms=%u sign_ms=%u sign_bytes=%u keygen_us=%u sign_us=%u"
		 " keygen_cycles=%u sign_cycles=%u cpu_hz=%u stack_unused=%u\n",
		 (unsigned)(last.keygen_us / 1000), (unsigned)(last.sign_us / 1000),
		 (unsigned)last.sign_bytes, (unsigned)last.keygen_us, (unsigned)last.sign_us,
		 (unsigned)last.keygen_cycles, (unsigned)last.sign_cycles,
		 (unsigned)SystemCoreClock, (unsigned)main_stack_unused());
	put(b);
}

static void handle(char *cmd)
{
	if (!strcmp(cmd, "PUB")) {
		if (!have_key) {
			put("ERR no key; send GEN\n");
			return;
		}
		put("PUB ");
		put_hex(pk, CRYPTO_PUBLICKEYBYTES);
		put("\n");
	} else if (!strncmp(cmd, "SIGN ", 5)) {
		cmd_sign(cmd + 5);
	} else if (!strcmp(cmd, "GEN")) {
		if (have_key) {
			put("ERR key exists; send GEN FORCE to replace it\n");
			return;
		}
		cmd_gen();
	} else if (!strcmp(cmd, "GEN FORCE")) {
		cmd_gen();
	} else if (!strcmp(cmd, "TIME")) {
		cmd_time();
	} else {
		put("ERR unknown\n");
	}
}

/* ---------------------------------------------------------------- main */

int main(void)
{
	/* Run the application core at 128 MHz (reset default is 64 MHz). */
	(void)nrfx_clock_divider_set(NRF_CLOCK_DOMAIN_HFCLK, NRF_CLOCK_HFCLK_DIV_1);
	SystemCoreClockUpdate();

	storage_rc = settings_subsys_init();
	if (!storage_rc) {
		storage_rc = settings_load_subtree("notary");
	}

	if (!device_is_ready(uart)) {
		return 0; /* nothing we can talk on */
	}
	uart_irq_callback_user_data_set(uart, uart_isr, NULL);
	uart_irq_rx_enable(uart);

	size_t len = 0;
	bool too_long = false;
	uint8_t chunk[128];

	for (;;) {
		k_sem_take(&rx_sem, K_FOREVER);
		for (;;) {
			unsigned int key = irq_lock();
			uint32_t got = ring_buf_get(&rx_ring, chunk, sizeof(chunk));

			irq_unlock(key);
			if (!got) {
				break;
			}
			for (uint32_t i = 0; i < got; i++) {
				char c = (char)chunk[i];

				if (c == '\n' || c == '\r') {
					if (atomic_cas(&rx_overrun, 1, 0)) {
						put("ERR overflow\n");
					} else if (too_long) {
						put("ERR too long\n");
					} else if (len) {
						line[len] = '\0';
						handle(line);
					}
					len = 0;
					too_long = false;
				} else if (len < sizeof(line) - 1) {
					line[len++] = c;
				} else {
					too_long = true;
				}
			}
		}
	}
	return 0;
}
