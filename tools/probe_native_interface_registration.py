#!/usr/bin/python3
"""One-shot native interface registration probe; no RF or network traffic."""

import os
import secrets
import sys
from pathlib import Path


def main():
    if len(sys.argv) != 2 or sys.argv[1] != "--apply" or os.geteuid() != 0:
        raise SystemExit("Uso: sudo python3 tools/probe_native_interface_registration.py --apply")

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "wifi"))
    from native_radio_control import NativeRadioPublisher

    publisher = NativeRadioPublisher.open_if_present()
    if publisher is None:
        raise SystemExit("Controlador AIC nativo não encontrado; nada foi alterado.")
    try:
        # Locally administered, unicast test address. Never publish a guessed
        # connected state or impersonate the live station using the USB radio.
        address = bytearray(secrets.token_bytes(6))
        address[0] = (address[0] | 0x02) & 0xfe
        publisher.publish(False, None, bytes(address))
        print("Estado de teste publicado: rádio desligado, sem associação.")
    finally:
        publisher.close()


if __name__ == "__main__":
    main()
