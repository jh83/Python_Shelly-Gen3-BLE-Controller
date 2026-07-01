#!/usr/bin/env python3
"""Control a Shelly Outdoor Plug S Gen3 relay over BLE JSON-RPC."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import struct
import sys
from typing import Any

from bleak import BleakClient, BleakScanner
from bleak.exc import BleakDeviceNotFoundError

SHELLY_GATT_SERVICE_UUID = "5f6d4f53-5f52-5043-5f53-56435f49445f"
RPC_CHAR_DATA_UUID = "5f6d4f53-5f52-5043-5f64-6174615f5f5f"
RPC_CHAR_TX_CTL_UUID = "5f6d4f53-5f52-5043-5f74-785f63746c5f"
RPC_CHAR_RX_CTL_UUID = "5f6d4f53-5f52-5043-5f72-785f63746c5f"

RPC_SRC = "shelly_ble_py"
CONNECT_TIMEOUT = 30.0
SCAN_TIMEOUT = 15.0
TX_DELAY_SECONDS = 0.5
RX_DELAY_SECONDS = 0.5
READ_CHUNK_DELAY_SECONDS = 0.3

MAC_PATTERN = re.compile(
    r"^([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$"
)


class ShellyRpcError(RuntimeError):
    """Raised when the Shelly device returns an RPC error."""


def normalize_mac(address: str) -> str:
    address = address.strip()
    if not MAC_PATTERN.match(address):
        raise ValueError(
            f"Invalid MAC address: {address!r}. "
            "Expected format AA:BB:CC:DD:EE:FF or AA-BB-CC-DD-EE-FF."
        )
    return address.replace("-", ":").upper()


def build_rpc_request(
    method: str,
    params: dict[str, Any] | None = None,
    request_id: int = 1,
) -> bytes:
    payload = {
        "id": request_id,
        "src": RPC_SRC,
        "method": method,
        "params": params or {},
    }
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


async def send_rpc(
    client: BleakClient,
    method: str,
    params: dict[str, Any] | None = None,
    request_id: int = 1,
) -> dict[str, Any]:
    request_data = build_rpc_request(method, params, request_id)
    length_bytes = struct.pack(">I", len(request_data))

    await client.write_gatt_char(RPC_CHAR_TX_CTL_UUID, length_bytes, response=True)
    await asyncio.sleep(TX_DELAY_SECONDS)
    await client.write_gatt_char(RPC_CHAR_DATA_UUID, request_data, response=True)

    rx_length_raw = await client.read_gatt_char(RPC_CHAR_RX_CTL_UUID)
    if len(rx_length_raw) < 4:
        raise RuntimeError(f"Unexpected RX control length: {len(rx_length_raw)} bytes")
    response_length = struct.unpack(">I", rx_length_raw[:4])[0]
    await asyncio.sleep(RX_DELAY_SECONDS)

    response_chunks: list[bytes] = []
    received = 0
    while received < response_length:
        chunk = await client.read_gatt_char(RPC_CHAR_DATA_UUID)
        if not chunk:
            raise RuntimeError("Empty read while receiving RPC response")
        response_chunks.append(chunk)
        received += len(chunk)
        if received < response_length:
            await asyncio.sleep(READ_CHUNK_DELAY_SECONDS)

    response_text = b"".join(response_chunks).decode("utf-8")
    response = json.loads(response_text)

    if response.get("id") != request_id:
        raise RuntimeError(
            f"RPC response id mismatch: expected {request_id}, got {response.get('id')}"
        )
    if "error" in response:
        raise ShellyRpcError(json.dumps(response["error"], indent=2))
    if "result" not in response:
        raise RuntimeError(f"RPC response missing result: {response_text}")
    return response["result"]


async def find_device(address: str, timeout: float = SCAN_TIMEOUT):
    normalized = normalize_mac(address)
    device = await BleakScanner.find_device_by_address(normalized, timeout=timeout)
    if device is None:
        raise BleakDeviceNotFoundError(
            normalized, f"Device with address {normalized} was not found."
        )
    return device


async def run_command(address: str, method: str, params: dict[str, Any] | None) -> dict[str, Any]:
    device = await find_device(address)
    async with BleakClient(
        device,
        timeout=CONNECT_TIMEOUT,
        winrt={"use_cached_services": False},
    ) as client:
        return await send_rpc(client, method, params)


async def scan_devices(duration: float) -> None:
    print(f"Scanning for BLE devices ({duration:.0f}s)...")
    discovered = await BleakScanner.discover(timeout=duration, return_adv=True)
    if not discovered:
        print("No BLE devices found.")
        return

    entries = sorted(
        discovered.values(),
        key=lambda item: item[1].rssi,
        reverse=True,
    )
    print("Address              RSSI  Name")
    print("-" * 60)
    for device, adv in entries:
        name = device.name or adv.local_name or ""
        marker = "  <-- Shelly?" if "shelly" in name.lower() else ""
        print(f"{device.address:<20} {adv.rssi:>4}  {name}{marker}")


def command_for_action(action: str) -> tuple[str, dict[str, Any]]:
    if action == "on":
        return "Switch.Set", {"id": 0, "on": True}
    if action == "off":
        return "Switch.Set", {"id": 0, "on": False}
    if action == "toggle":
        return "Switch.Toggle", {"id": 0}
    if action == "status":
        return "Switch.GetStatus", {"id": 0}
    raise ValueError(f"Unknown action: {action}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Control a Shelly Outdoor Plug S Gen3 relay over BLE."
    )
    parser.add_argument(
        "--address",
        "-a",
        help="BLE MAC address of the Shelly device (AA:BB:CC:DD:EE:FF)",
    )
    parser.add_argument(
        "--scan-duration",
        type=float,
        default=10.0,
        help="Seconds to scan when using the scan command (default: 10)",
    )
    parser.add_argument(
        "action",
        choices=["on", "off", "toggle", "status", "scan"],
        help="Relay action or BLE scan",
    )
    return parser


async def async_main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.action == "scan":
        await scan_devices(args.scan_duration)
        return 0

    if not args.address:
        parser.error("--address is required for on/off/toggle/status")

    method, params = command_for_action(args.action)
    try:
        result = await run_command(args.address, method, params)
    except BleakDeviceNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        print(
            "Tip: run 'python shelly_ble_control.py scan' to find nearby devices.",
            file=sys.stderr,
        )
        return 1
    except ShellyRpcError as exc:
        print(f"RPC error from device:\n{exc}", file=sys.stderr)
        return 1
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    if args.action in {"on", "off", "toggle"}:
        output = result.get("output")
        if output is not None:
            state = "ON" if output else "OFF"
            print(f"Relay is now {state}.")
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
