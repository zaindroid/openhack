# nRF5340 Notary: ML-DSA-44 signer on the nRF5340 DK (Zephyr / nRF Connect SDK)

The board holds the signing key and the host never sees it. Firmware for the **application core** of the nRF5340 DK
(`nrf5340dk/nrf5340/cpuapp`, Cortex-M33F, set to 128 MHz at boot). It talks over **UART0**, which the DK's on-board
J-Link exposes as a virtual COM port (115200 8N1, no flow control). No USB device stack is used and nothing is written
to the UART unless a command asks for it: console, printk, logging and the boot banner are all disabled.

## Protocol (one reply line per command line)

```
host -> PUB\n                 board -> PUB <public key hex, 1312 bytes>\n
host -> SIGN <msg hex>\n      board -> SIG <signature hex, 2420 bytes>\n      (message 0..2048 bytes)
host -> GEN\n                 board -> OK keygen <n> ms\n                       (only if no key is stored yet)
host -> GEN FORCE\n           board -> OK keygen <n> ms\n                       (replaces the stored key)
host -> TIME\n                board -> TIME keygen_ms=<n> sign_ms=<n> sign_bytes=<n> keygen_us=<n> sign_us=<n>
                                          keygen_cycles=<n> sign_cycles=<n> cpu_hz=<n> stack_unused=<n>\n
anything else / failures      board -> ERR <reason>\n
```

`ERR` reasons: `no key; send GEN`, `key exists; send GEN FORCE to replace it`, `hex` (odd length, non-hex digit or
more than 2048 bytes), `too long`, `overflow`, `entropy` (the RNG failed, so the result was thrown away), `sign`,
`keygen <rc>`, `save <rc>`, `storage <rc>`, `unknown`.

Signatures are pure ML-DSA-44 (FIPS 204) with an empty context string, so `dilithium_py.ml_dsa.ML_DSA_44.verify(pk,
msg, sig)` checks them; `notary/verify.py` and `notary/serve.py` already do this. TIME reports the last GEN and SIGN
since boot. `*_ms` and `*_us` are wall time from the 32 kHz kernel clock (30.5 µs resolution), `*_cycles` is the
DWT cycle counter, and `stack_unused` is how much of the 56 KB main stack has never been touched.

`app/notary.py` (`SerialSigner`) and `notary/serve.py` (`Board`) open the port at 115200, write `<cmd>\n`, read one
line and check it starts with `PUB ` or `SIG `. The firmware keeps to that.

## Layout

```
notary/nrf5340/
  CMakeLists.txt         app; adds modules/pqm4 to ZEPHYR_EXTRA_MODULES
  prj.conf               UART0 (IRQ RX), no console/log, settings+NVS, CSPRNG, FPU, pqm4 m4f, 56 KB main stack
  src/main.c             protocol, key storage, timing
  modules/pqm4/          Zephyr module wrapper for pqm4 (no pqm4 sources are vendored)
    zephyr/module.yml
    Kconfig              CONFIG_PQM4_MLDSA44, choice M4F (default) / M4FSTACK, PQM4_OPTIMIZE_SPEED, PQM4_RANDOMBYTES
    CMakeLists.txt       compiles crypto_sign/ml-dsa-44/<impl>/*.{c,S,s} + mupq/common/fips202.c + common/keccakf1600.S
    zephyr/randombytes_zephyr.c   randombytes() -> sys_csrand_get(); on failure zeroes the buffer and counts it
    shim/randombytes.h, include/pqm4_zephyr.h
  tests/qemu_selftest/   keygen+sign+verify on QEMU (Cortex-M55), plus verify.py (dilithium-py cross-check)
  tools/measure.py       timing over serial and over serve.py
  build-out/             build artifacts (gitignored)
```

**pqm4 version:** `mupq/pqm4` at `e1146b1bc180c66689682f6ce63bd8f126a51ace`, with only the `mupq` submodule
(`3bce0c95e9ae11d97daa7285f84bf2e1a90ad451`). `libopencm3` and `mupq/pqclean` are not needed. The module looks for
the checkout in `PQM4_DIR` (environment variable or `-DPQM4_DIR=`), and otherwise in
`<west workspace>/modules/crypto/pqm4`.

**Implementation choice:** `m4f`. The app core is a Cortex-M33 with the DSP extension and a single-precision FPU, so it
runs pqm4's Cortex-M4F assembly unchanged. That code uses the FPU registers as spill space, which is why `CONFIG_FPU`
and `CONFIG_FPU_SHARING` are on. pqm4's own benchmarks give:

| impl     | keygen cycles | sign cycles (avg) | verify cycles | stack keygen / sign |
|----------|---------------|-------------------|---------------|---------------------|
| m4f      | 1.43 M        | 3.94 M            | 1.42 M        | 38.3 KB / 44.8 KB   |
| m4fstack | 1.80 M        | 12.1 M            | 3.24 M        | 4.4 KB / 5.1 KB     |

At 128 MHz, m4f signs in about 31 ms on average and m4fstack in about 95 ms. The app core has 512 KB of RAM, so
spending 56 KB on the main stack for a 3x faster signer is an easy trade. In the QEMU self-test, m4f used 44,992 bytes
of the 57,344-byte stack. If RAM ever gets tight, switch to `CONFIG_PQM4_MLDSA44_M4FSTACK=y` and lower
`CONFIG_MAIN_STACK_SIZE` to about 12 KB.

**Entropy:** on `nrf5340dk/nrf5340/cpuapp` in NCS v3.4.1, `zephyr,entropy` is the app core's CryptoCell-312
(`CONFIG_ENTROPY_CC3XX` with `CONFIG_NRF_CC3XX_PLATFORM`). `CONFIG_ENTROPY_GENERATOR=y` is enough to get
`CONFIG_CSPRNG_ENABLED` / `HARDWARE_DEVICE_CS_GENERATOR`, and the network core is not involved. The randombytes shim
will not compile without a CSPRNG. ML-DSA signing in pqm4 is hedged, so it calls `randombytes()` on every SIGN as
well as on GEN.

**Key storage:** pk‖sk are stored as one settings entry, `notary/key` (3872 bytes), in the DTS `storage_partition`
(0xf8000, 32 KB, NVS with 8 sectors). Because it is a single entry, it is written in one go. `west flash` erases only
the pages the image touches, so reflashing keeps the key. `west flash --erase` or a full chip erase wipes it.

## Built here (servingz, NCS v3.4.1)

- Toolchain container `ghcr.io/nrfconnect/sdk-nrf-toolchain:v3.4.1`, workspace `~/ncs-v3.4.1`, pqm4 in
  `~/ncs-v3.4.1/modules/crypto/pqm4`.
- `nrf5340dk/nrf5340/cpuapp`: **FLASH 75,856 B (7.2 % of 1 MB), RAM 84,464 B (18.4 % of 448 KB)**, of which 56 KB is
  the main stack and 8 KB the RX ring buffer. pqm4 adds about 31 KB of code. The build is a single image with no
  MCUboot or Partition Manager, so there is no `merged.hex`. `zephyr.hex` is the file you flash.
- Artifacts: `servingz:~/apps/openhack-nrf/notary/nrf5340/build-out/{zephyr.hex,zephyr.bin,zephyr.elf}` and
  `servingz:~/mosca-firmware/{zephyr.hex,zephyr.bin}`.
- QEMU self-test (`mps3/corstone300/an547`, Cortex-M55 with DSP and FPU): keygen, sign over 2048 bytes and verify all
  succeed, a tampered signature is rejected, and the signature verifies with dilithium-py.

Rebuild on servingz:

```bash
docker run --rm --name lab-mosca-nrf-build --user $(id -u):$(id -g) -e HOME=/ncs/.home \
  -v ~/ncs-v3.4.1:/ncs -v ~/apps/openhack-nrf:/work -w /ncs ghcr.io/nrfconnect/sdk-nrf-toolchain:v3.4.1 \
  "west build -b nrf5340dk/nrf5340/cpuapp -d /work/notary/nrf5340/build /work/notary/nrf5340"
```

## On the laptop (Windows)

### 0. Fastest: flash the prebuilt image

You need **nrfutil** (from nordicsemi.com, or through nRF Connect for Desktop) with the `device` command, and the
**SEGGER J-Link** software (nrfutil prompts you to install it).

```powershell
nrfutil install device
scp servingz-ts:~/mosca-firmware/zephyr.hex $env:USERPROFILE\mosca-notary.hex
nrfutil device list                                   # shows the DK's serial number and its COM ports
nrfutil device program --firmware $env:USERPROFILE\mosca-notary.hex --core Application `
  --options chip_erase_mode=ERASE_RANGES_TOUCHED_BY_FIRMWARE,verify=VERIFY_READ
nrfutil device reset
```

### 1. Native build (nrfutil sdk-manager + west)

```powershell
nrfutil install sdk-manager
nrfutil sdk-manager install v3.4.1                    # SDK in C:\ncs\v3.4.1, toolchain in C:\ncs\toolchains\...
nrfutil sdk-manager toolchain launch --ncs-version v3.4.1 --shell    # shell with west, cmake, ninja, gcc on PATH
# in that shell:
git clone https://github.com/mupq/pqm4 C:\ncs\v3.4.1\modules\crypto\pqm4
cd C:\ncs\v3.4.1\modules\crypto\pqm4
git checkout e1146b1bc180c66689682f6ce63bd8f126a51ace
git submodule update --init mupq                      # NOT --recursive: pqclean and libopencm3 are not needed
cd <path to openhack>
west build -b nrf5340dk/nrf5340/cpuapp -d notary\nrf5340\build notary\nrf5340
west flash -d notary\nrf5340\build                    # J-Link on the DK, nrfutil runner; keeps the stored key
```

If pqm4 lives somewhere else, run `$env:PQM4_DIR = "D:\src\pqm4"` before `west build`. With the nRF Connect for VS
Code extension, open `notary\nrf5340` as an application, pick board `nrf5340dk/nrf5340/cpuapp` and SDK v3.4.1, and
set `PQM4_DIR` in the environment the same way.

### 2. Container build (Docker Desktop), then flash natively

```powershell
docker volume create ncs-v3.4.1
docker run --rm -v ncs-v3.4.1:/ncs -w /ncs ghcr.io/nrfconnect/sdk-nrf-toolchain:v3.4.1 `
  "west init -m https://github.com/nrfconnect/sdk-nrf --mr v3.4.1 && west update --narrow -o=--depth=1 && \
   git clone -q https://github.com/mupq/pqm4 modules/crypto/pqm4 && cd modules/crypto/pqm4 && \
   git checkout -q e1146b1bc180c66689682f6ce63bd8f126a51ace && git submodule update -q --init mupq"
docker run --rm -v ncs-v3.4.1:/ncs -v ${PWD}:/work -w /ncs ghcr.io/nrfconnect/sdk-nrf-toolchain:v3.4.1 `
  "west build -b nrf5340dk/nrf5340/cpuapp -d /work/notary/nrf5340/build /work/notary/nrf5340"
nrfutil device program --firmware notary\nrf5340\build\nrf5340\zephyr\zephyr.hex --core Application `
  --options chip_erase_mode=ERASE_RANGES_TOUCHED_BY_FIRMWARE,verify=VERIFY_READ
nrfutil device reset
```

(Run from the repository root. USB passthrough into Docker on Windows is awkward, which is why flashing is done
natively.)

### 3. Find the COM port

The DK shows up as *JLink CDC UART Port (COMx)*, two or three of them. The application core's UART0 is **VCOM0**,
which is normally the lowest-numbered one.

```powershell
nrfutil device list                                                   # lists the VCOM ports per DK
Get-CimInstance Win32_PnPEntity | ? Name -like 'JLink CDC UART*' | select Name
python -m serial.tools.list_ports -v
```

To check quickly, send `TIME` to each port. The right one answers with a `TIME ...` line.

### 4. Provision (once)

```powershell
pip install pyserial httpx dilithium-py fastapi uvicorn
python -c "import serial; s=serial.Serial('COM5',115200,timeout=30); s.write(b'GEN\n'); print(s.readline()); s.write(b'TIME\n'); print(s.readline())"
```

The reply should be `OK keygen <n> ms`. Run `GEN` once. Later `GEN` calls return `ERR key exists` so the published
key cannot be replaced by accident; `GEN FORCE` replaces it on purpose.

### 5. Measure

```powershell
python notary\nrf5340\tools\measure.py --serial COM5 --n 20          # (--gen if not provisioned yet)
```

This prints the `TIME` line after GEN (if `--gen`) and after the first SIGN, plus serial round-trip
median/min/max for 52-byte messages (the size of an attestation: 32-byte chain root plus run id). It also signs one
2048-byte message and verifies every signature with dilithium-py. Note down `sign_ms`, `sign_cycles`, `keygen_ms`,
`cpu_hz` (should be 128000000), `stack_unused`, and the serial round trip. The round trip is mostly UART time: about
5 KB of hex moves at 115200 baud, roughly 0.45 s, so on-device signing is a small part of it.

Then measure through the bridge. Stop `measure.py` first, because only one program can hold the COM port:

```powershell
$env:NOTARY_TOKEN = "<random, >= 24 chars>"
python notary\serve.py --serial COM5 --host 127.0.0.1 --port 8099      # terminal 1
python notary\nrf5340\tools\measure.py --url http://127.0.0.1:8099 --n 20   # terminal 2
```

### 6. Serve to servingz over Tailscale

```powershell
$env:NOTARY_TOKEN = "<same random token as in Coolify>"
python notary\serve.py --serial COM5 --host 100.84.181.5 --port 8099
# firewall: allow 8099 only from the tailnet (Tailscale's CGNAT range) on the Tailscale interface
New-NetFirewallRule -DisplayName "Mosca notary (Tailscale)" -Direction Inbound -Protocol TCP -LocalPort 8099 `
  -LocalAddress 100.84.181.5 -RemoteAddress 100.64.0.0/10 -InterfaceAlias Tailscale -Action Allow
```

On servingz, the `lab-mosca` app in Coolify needs `NOTARY_URL=http://100.84.181.5:8099` and the same `NOTARY_TOKEN`.
`app/notary.py` checks `NOTARY_URL` first. If the bridge is unreachable it falls back to the software signer and the
attestation records why. Check from servingz:
`curl -s -H "Authorization: Bearer $NOTARY_TOKEN" http://100.84.181.5:8099/pub`.

## Troubleshooting

- No reply, or garbled replies on long `SIGN` lines: the J-Link Mass Storage Device can cause dropped VCOM bytes on
  nRF DKs. Run `JLink.exe`, then `MSDDisable`, then power-cycle the DK.
- `ERR storage -<n>`: settings or NVS failed to initialise, usually because the storage partition was overwritten.
  Erase the partition with `nrfutil device erase --all` and reflash (this destroys the key; run GEN afterwards).
- `ERR entropy`: the CryptoCell RNG failed and nothing was signed or stored. Reset the board.

## Checklist for the human at the laptop

1. Install nrfutil (`device`, optionally `sdk-manager`) and the SEGGER J-Link software. Plug in the DK (USB on the
   J-Link side, power switch ON).
2. Flash: route 0 (prebuilt `zephyr.hex` from `servingz:~/mosca-firmware/`) or build with route 1 or 2.
3. Find the COM port (VCOM0) and check that `TIME` gets an answer.
4. `GEN` once and note the `OK keygen <n> ms` line.
5. `tools/measure.py --serial COMx --n 20`, then record keygen_ms, sign_ms, sign_cycles, cpu_hz, stack_unused and the
   serial round trip. Then run `serve.py` on 127.0.0.1 with `measure.py --url` and record the HTTP round trip. Put
   the numbers in the demo.
6. Start `notary\serve.py --serial COMx --host 100.84.181.5 --port 8099` with a long random `NOTARY_TOKEN`.
7. Open Windows Firewall for TCP 8099 on the Tailscale interface only (rule above).
8. In Coolify (lab-mosca), set `NOTARY_URL=http://100.84.181.5:8099` and `NOTARY_TOKEN=<same token>`, redeploy, run
   one job, and check that the attestation's `signer` reads `nRF5340 (hardware) via http://100.84.181.5:8099` and
   that `python notary/verify.py <attestation.json>` prints VERIFIED.
