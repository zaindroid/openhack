/* Mosca Notary — ML-DSA-44 signer on the nRF5340 application core.
 * Line protocol over USB-CDC: PUB | SIGN <hex> | GEN. The private key never leaves the device (settings/NVS).
 * Crypto: pqm4 ML-DSA-44 (FIPS 204) — api.h provides crypto_sign_keypair / crypto_sign_signature.
 */
#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/usb/usb_device.h>
#include <zephyr/settings/settings.h>
#include <zephyr/random/random.h>
#include <string.h>
#include <stdio.h>
#include "api.h"                     /* pqm4 mldsa44: CRYPTO_PUBLICKEYBYTES 1312, CRYPTO_SECRETKEYBYTES 2560, CRYPTO_BYTES 2420 */

static uint8_t pk[CRYPTO_PUBLICKEYBYTES];
static uint8_t sk[CRYPTO_SECRETKEYBYTES];
static uint8_t sig[CRYPTO_BYTES];
static bool have_key;
static char line[8192];
static uint8_t msg[2048];

static int settings_set(const char *name, size_t len, settings_read_cb read_cb, void *cb_arg)
{
	if (!strcmp(name, "sk") && len == sizeof(sk)) { read_cb(cb_arg, sk, len); have_key = true; return 0; }
	if (!strcmp(name, "pk") && len == sizeof(pk)) { read_cb(cb_arg, pk, len); return 0; }
	return -ENOENT;
}
SETTINGS_STATIC_HANDLER_DEFINE(notary, "notary", NULL, settings_set, NULL, NULL);

static void put(const struct device *dev, const char *s) { while (*s) uart_poll_out(dev, *s++); }
static void put_hex(const struct device *dev, const uint8_t *b, size_t n)
{
	static const char *h = "0123456789abcdef";
	for (size_t i = 0; i < n; i++) { uart_poll_out(dev, h[b[i] >> 4]); uart_poll_out(dev, h[b[i] & 15]); }
}
static int unhex(const char *s, uint8_t *out, size_t max)
{
	size_t n = strlen(s) / 2; if (n > max) return -1;
	for (size_t i = 0; i < n; i++) { unsigned v; if (sscanf(s + 2 * i, "%2x", &v) != 1) return -1; out[i] = v; }
	return (int)n;
}

static void handle(const struct device *dev, char *cmd)
{
	if (!strcmp(cmd, "PUB")) {
		if (!have_key) { put(dev, "ERR no key; send GEN\n"); return; }
		put(dev, "PUB "); put_hex(dev, pk, sizeof(pk)); put(dev, "\n");
	} else if (!strcmp(cmd, "GEN")) {
		int64_t t0 = k_uptime_get();
		crypto_sign_keypair(pk, sk);            /* randombytes() wired to sys_csrand_get in the module */
		settings_save_one("notary/sk", sk, sizeof(sk)); settings_save_one("notary/pk", pk, sizeof(pk));
		have_key = true;
		char b[64]; snprintf(b, sizeof(b), "OK keygen %lld ms\n", k_uptime_get() - t0); put(dev, b);
	} else if (!strncmp(cmd, "SIGN ", 5)) {
		if (!have_key) { put(dev, "ERR no key\n"); return; }
		int n = unhex(cmd + 5, msg, sizeof(msg)); if (n < 0) { put(dev, "ERR hex\n"); return; }
		size_t siglen = 0; int64_t t0 = k_uptime_get();
		if (crypto_sign_signature(sig, &siglen, msg, n, sk) != 0) { put(dev, "ERR sign\n"); return; }
		put(dev, "SIG "); put_hex(dev, sig, siglen); put(dev, "\n");
		printk("signed %d bytes in %lld ms\n", n, k_uptime_get() - t0);
	} else {
		put(dev, "ERR unknown\n");
	}
}

int main(void)
{
	const struct device *dev = DEVICE_DT_GET(DT_CHOSEN(zephyr_console));
	usb_enable(NULL);
	settings_subsys_init(); settings_load();
	size_t len = 0; unsigned char c;
	while (1) {
		while (uart_poll_in(dev, &c) == 0) {
			if (c == '\n' || c == '\r') { if (len) { line[len] = 0; handle(dev, line); len = 0; } }
			else if (len < sizeof(line) - 1) line[len++] = c;
		}
		k_msleep(1);
	}
	return 0;
}
