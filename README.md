# Home Assistant Lippert OneControl Integration

[![GitHub Release][releases-shield]][releases]
[![License][license-shield]](LICENSE)

Control your RV's Lippert OneControl system directly from Home Assistant!

## Features

- **💡 Light Control**: Turn lights ON/OFF
  - Kitchen Ceiling
  - Living Room Ceiling
  - Bed Ceiling
  - Porch Light
  - Awning Light
  - Scare Light

- **📊 Tank Sensors**: Monitor levels
  - Fresh Water
  - Grey Water
  - Black Water
  - LP Gas (Propane)

- **🔋 Battery Voltage**: Real-time monitoring

- **⏱️ Generator Hours**: Track runtime

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click the three dots in the top right
3. Select "Custom repositories"
4. Add `https://github.com/manos/HomeAssistant-Lippert-OneControl-Integration` as Integration
5. Install "Lippert OneControl"
6. Restart Home Assistant

### Manual Installation

1. Copy `custom_components/lippert_onecontrol` to your Home Assistant's `custom_components` directory
2. Restart Home Assistant

## Configuration

1. Go to **Settings → Devices & Services**
2. Click **+ Add Integration**
3. Search for "Lippert OneControl"
4. Enter your controller's IP address (default: `192.168.1.1`)

> **Note:** You must be connected to your RV's WiFi network for the integration to work.

## Network Requirements

The OneControl controller typically runs on:
- **IP:** `192.168.1.1`
- **Port:** `6969`

Your Home Assistant instance must be able to reach this IP. Options:
1. Connect HA to your RV's WiFi network
2. Bridge your RV WiFi to your home network
3. Use a dual-interface setup

## Known Devices

| Counter | Device | Type |
|---------|--------|------|
| 0x28 | Kitchen Ceiling Light | Light |
| 0x77 | Living Room Ceiling Light | Light |
| 0xFB | Bed Ceiling Light | Light |
| 0xCF | Porch Light | Light |
| 0x15 | Awning Light | Light |
| 0xFF | Scare Light | Light |
| 0x3E | Fresh Tank | Sensor |
| 0x04 | Grey Tank | Sensor |
| 0x86 | Black Tank | Sensor |
| 0x10 | LP Tank | Sensor |

## Protocol Details

This integration uses the reverse-engineered Lippert OneControl protocol:
- COBS-encoded frames over TCP
- CRC-8/MAXIM checksums
- TEA cipher authentication for device control

For technical details, see the [OneControl-RV-C-Protocol](https://github.com/manos/OneControl-RV-C-Protocol) repository.

## Safety Notice

⚠️ **This integration only controls lights.** Water heaters, slides, awnings, levelers, and other motorized equipment require additional safety considerations and are not included in this release.

## Troubleshooting

### Cannot Connect
- Verify you're on the RV WiFi network
- Check that the controller IP is correct
- Ensure no firewall is blocking port 6969

### Lights Not Responding
- The integration requires a fresh TCP connection for each command
- If commands fail, try again after a few seconds
- The OneControl app should be closed (it may hold the connection)

### Sensors Not Updating
- Tank levels and battery voltage are polled every 30 seconds
- Some sensors require the RV's electrical system to be active

## Contributing

Contributions are welcome! Please see the protocol documentation for technical details.

## License

MIT License - see [LICENSE](LICENSE) for details.

---

[releases-shield]: https://img.shields.io/github/release/manos/HomeAssistant-Lippert-OneControl-Integration.svg
[releases]: https://github.com/manos/HomeAssistant-Lippert-OneControl-Integration/releases
[license-shield]: https://img.shields.io/github/license/manos/HomeAssistant-Lippert-OneControl-Integration.svg
