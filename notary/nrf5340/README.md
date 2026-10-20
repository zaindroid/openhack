# nRF5340 Notary — ML-DSA-44 signer over USB-CDC (Zephyr)

The board holds the signing key; the host never sees it. Same line protocol as `app/notary.py::SerialSigner`:

```
host → PUB\n                    board → PUB <pk hex 1312 bytes>\n
host → SIGN <msg hex>\n         board → SIG <sig hex 2420 bytes>\n
host → GEN\n                    board → OK (new keypair, stored in settings NVS)   # provisioning only
```

## Build
Requires nRF Connect SDK (Zephyr) and the pqm4 ML-DSA-44 sources as a Zephyr module (`crypto_sign_keypair`,
`crypto_sign_signature` from `mldsa44/`). Expected RAM/flash on the nRF5340 app core: ~60 KB RAM, ~120 KB flash for
ML-DSA-44; signing takes tens of milliseconds at 128 MHz (measure and put the number in the demo).

```
west build -b nrf5340dk/nrf5340/cpuapp notary/nrf5340
west flash
python -c "import serial; s=serial.Serial('/dev/ttyACM0',115200); s.write(b'GEN\n'); print(s.readline())"
NOTARY_SERIAL=/dev/ttyACM0 uvicorn whycore.app:app --port 8080     # attestations now say "nRF5340 (hardware)"
```

`verify.py` accepts both ML-DSA-44 (board) and ML-DSA-65 (software) attestations.

## Status
Firmware skeleton: UART protocol and key storage are written; the pqm4 module path and the measured timings must be
filled in on the board (not buildable in the repo's CI). Fallback: the software signer, which the UI labels clearly.
