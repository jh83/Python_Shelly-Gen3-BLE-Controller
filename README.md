# Shelly Outdoor Plug S Gen3 — BLE Relay Control

Python script to turn the relay on or off on a **Shelly Outdoor Plug S Gen3** over Bluetooth Low Energy (BLE), using Shelly's JSON-RPC GATT protocol.

Tested on Windows 11 with Python 3.10+.

## Requirements

- Shelly Outdoor Plug S Gen3 (or other Shelly Gen2+/Gen3 device with BLE RPC)
- Bluetooth enabled on the plug (Settings → Bluetooth in the device web UI; enabled by default)
- Plug powered on and within BLE range (~10 m)
- Python 3.10+
- Working Bluetooth on your PC

## Setup

```powershell
pip install -r requirements.txt
```

## Find your device

Scan for nearby BLE devices. Shelly plugs appear with names like `ShellyOutdoorSG3-...`:

```powershell
python shelly_ble_control.py scan
```

Use the **Address** column as your MAC address (e.g. `E4:B0:63:F3:55:62`).

## Usage

```powershell
# Turn relay on
python shelly_ble_control.py -a AA:BB:CC:DD:EE:FF on

# Turn relay off
python shelly_ble_control.py -a AA:BB:CC:DD:EE:FF off

# Toggle relay
python shelly_ble_control.py -a AA:BB:CC:DD:EE:FF toggle

# Read relay status (output, voltage, power, temperature, etc.)
python shelly_ble_control.py -a AA:BB:CC:DD:EE:FF status
```

### Status response

The `status` command calls `Switch.GetStatus` and prints the `result` object from the device. Example:

```json
{
  "id": 0,
  "source": "GATTS",
  "output": true,
  "apower": 25.0,
  "voltage": 239.3,
  "freq": 50.0,
  "current": 0.111,
  "aenergy": {
    "total": 0.0,
    "by_minute": [0.0, 0.0, 0.0],
    "minute_ts": 1782912420
  },
  "ret_aenergy": {
    "total": 0.0,
    "by_minute": [0.0, 0.0, 0.0],
    "minute_ts": 1782912420
  },
  "temperature": {
    "tC": 44.7,
    "tF": 112.5
  }
}
```

| Field | Meaning |
|-------|---------|
| `id` | Switch component index. Always `0` on the Outdoor Plug S (single relay). |
| `source` | What last changed the relay state. `GATTS` means BLE GATT (this script). Other values include `http` (web/API), `WS_in` (web UI), `init` (boot), `button`, `schedule`, etc. |
| `output` | **Relay state.** `true` = on, `false` = off. This is the main field for on/off status. |
| `apower` | Instantaneous active power drawn by the load, in **watts** (W). `0` when off or nothing plugged in. |
| `voltage` | Mains voltage at the plug, in **volts** (V). |
| `freq` | Mains frequency, in **hertz** (Hz). Typically ~50 (EU) or ~60 (US). |
| `current` | Current through the relay, in **amperes** (A). |
| `aenergy` | **Consumed** energy counter (forward/active energy). |
| `aenergy.total` | Total energy consumed since last counter reset, in **watt-hours** (Wh). |
| `aenergy.by_minute` | Energy used in each of the last three full minutes, in **milliwatt-hours** (mWh). Index `0` is the minute before `minute_ts`. |
| `aenergy.minute_ts` | Unix timestamp (UTC) for the start of the current minute; anchors the `by_minute` buckets. |
| `ret_aenergy` | **Returned** energy counter (reverse/active energy, e.g. solar feed-back). Same structure as `aenergy`. On a simple plug with no generation, `total` is usually `0`. |
| `temperature.tC` | Internal device temperature, **degrees Celsius**. |
| `temperature.tF` | Internal device temperature, **degrees Fahrenheit**. |

Other fields may appear depending on firmware (e.g. `timer_started_at`, `tag`, `counts`) — see [Shelly Switch.GetStatus docs](https://shelly-api-docs.shelly.cloud/gen2/ComponentsAndServices/Switch#switchgetstatus).

MAC addresses can use colons or hyphens: `AA:BB:CC:DD:EE:FF` or `AA-BB-CC-DD-EE-FF`.

### Options

| Option | Description |
|--------|-------------|
| `-a`, `--address` | BLE MAC address (required for on/off/toggle/status) |
| `--scan-duration` | Scan time in seconds for `scan` command (default: 10) |

Exit code is `0` on success, non-zero on failure.

## How it works

The script connects via [bleak](https://github.com/hbldh/bleak), sends a JSON-RPC request over Shelly's BLE GATT service, and reads the response:

1. Connect to the device by MAC (with a pre-scan on Windows)
2. Write the request length to the TX Control characteristic
3. Write the JSON-RPC payload to the Data characteristic
4. Read the response length from RX Control, then read the response from Data

Relay commands use switch id `0`:

- `Switch.Set` — `on` / `off`
- `Switch.Toggle` — `toggle`
- `Switch.GetStatus` — `status`

Protocol details: [Shelly BLE RPC documentation](https://kb.shelly.cloud/knowledge-base/kbsa-communicating-with-shelly-devices-via-bluetoo).

## Device compatibility

This script was written and tested for the **Shelly Outdoor Plug S Gen3**, but only part of it is device-specific.

### What's generic (shared across Shelly Gen2+ / Gen3)

The BLE transport layer is the same on all Shelly Gen2+ and Gen3 devices that support BLE RPC:

- GATT service and characteristic UUIDs
- JSON-RPC request/response framing over BLE
- Connection handling (including Windows workarounds)

That protocol is documented by Shelly for the whole Gen2+/Gen3 family, not just the Outdoor Plug S.

### What's hard-coded (relay-specific)

The CLI commands map to **Switch** RPC methods with **component id `0`**:

| CLI action | RPC method | Params |
|------------|------------|--------|
| `on` | `Switch.Set` | `{"id": 0, "on": true}` |
| `off` | `Switch.Set` | `{"id": 0, "on": false}` |
| `toggle` | `Switch.Toggle` | `{"id": 0}` |
| `status` | `Switch.GetStatus` | `{"id": 0}` |

So in practice this is a **"control switch/relay #0 over BLE"** tool. The Outdoor Plug S name in the title reflects what was tested, not a separate protocol.

### Which devices work as-is?

| Device type | Works with current CLI? | Notes |
|-------------|-------------------------|-------|
| Single-relay Gen2+/Gen3 (Mini 1, 1 Gen3, Plug S, Outdoor Plug S, …) | **Yes** | Switch id `0` is correct |
| Multi-relay Gen2+/Gen3 (Plus 2PM, 2PM Gen3, 4Pro, …) | **Partially** | Only channel `0`; other channels need a different id |
| Dimmers (Dimmer Gen3, Plus Dimmer, …) | **No** | Uses `Light.Set` / `Light.GetStatus`, not `Switch.*` |
| Covers / rollers | **No** | Uses `Cover.Open`, `Cover.Close`, `Cover.GetStatus`, etc. |
| Sensors (H&T Gen3, BLU sensors, …) | **No** | No switch component to control |
| Wave (Z-Wave) devices | **No** | Different protocol; no Shelly BLE RPC |

BLE must be enabled on the device (Settings → Bluetooth in the web UI). Wave devices are out of scope entirely.

### Should you add support for other Gen3 types?

**Probably not yet**, unless you have a concrete use case.

| Approach | Worth it? | Why |
|----------|-----------|-----|
| `--switch-id N` for multi-relay devices | **Yes, low effort** | Same `Switch.*` API; easy to test on your plug (always id `0`) and likely works on dual-relay devices |
| Generic `rpc` command (pass any method + JSON params) | **Yes, medium effort** | Reuses the existing `send_rpc()` layer; you can probe unknown devices without guessing CLI actions |
| Built-in dimmer / cover / sensor commands | **Only if you own the hardware** | RPC method names and params differ per component type; without a device to test, errors are likely and hard to debug |

Shelly's RPC surface is well documented, so unvalidated code might *work*, but you would be shipping behavior you cannot verify. A small, honest extension (switch id + raw RPC) gives flexibility without maintaining a matrix of untested device profiles.

**Recommendation:** keep the current relay-focused CLI for your plug; add `--switch-id` and/or a `rpc` subcommand when you need broader coverage — not a full dimmer/cover implementation until you can test on real hardware.

## Troubleshooting

| Problem | What to try |
|---------|-------------|
| Device not found | Run `scan`, move closer to the plug, ensure Bluetooth is on |
| Connection hangs | Wait up to 30 s; retry after a few seconds |
| GATT characteristic error | Retry the command (can happen on rapid back-to-back runs on Windows) |
| RPC error in output | Check that Bluetooth is enabled on the Shelly device |

No Wi-Fi or Shelly Cloud account is required for BLE control.

## Files

- `shelly_ble_control.py` — CLI script
- `requirements.txt` — Python dependencies (`bleak`)
