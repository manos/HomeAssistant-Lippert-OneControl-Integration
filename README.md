# Home Assistant Lippert OneControl Integration

[![GitHub Release][releases-shield]][releases]
[![License][license-shield]](LICENSE)

Control your RV's Lippert OneControl system directly from Home Assistant!

## Features

- **💡 Light Control**: Turn RV lights ON/OFF
  - Ceiling lights, porch lights, awning lights, scare lights, and more
  - Automatic discovery of installed lights

- **📊 Tank Sensors**: Monitor tank levels
  - Fresh Water
  - Grey Water
  - Black Water
  - LP Gas (Propane)

- **🔋 Battery Voltage**: Real-time chassis battery monitoring

- **⚡ Generator Control**: Start/stop your generator
  - Power switch (ON/OFF)
  - State monitoring (Off, Priming, Starting, Running, Stopping)
  - Hour meter tracking

- **🔄 Auto-Discovery**: Automatically finds devices installed in your RV
  - No manual configuration of device IDs needed
  - Rediscover devices anytime via Configure menu

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
5. The integration will auto-discover your installed devices

### Rediscovering Devices

If you add new devices to your RV or update the integration:

1. Go to **Settings → Devices & Services → Integrations**
2. Find **Lippert OneControl** → click **Configure**
3. Select **🔄 Rediscover Devices**
4. New devices will be added without affecting existing ones

## Network Setup

The OneControl controller runs on the RV's internal WiFi network:
- **IP:** `192.168.1.1`
- **Port:** `6969`

Your Home Assistant instance must be able to reach this IP. 

### Recommended: Raspberry Pi Bridge

The easiest way to integrate OneControl with your home network is using a **Raspberry Pi as a network bridge**:

```
┌─────────────┐      WiFi       ┌──────────────┐     Ethernet    ┌─────────────┐
│  OneControl │  ────────────►  │ Raspberry Pi │  ─────────────► │    Home     │
│  Controller │   192.168.1.x   │   (bridge)   │   Your LAN      │  Assistant  │
│ 192.168.1.1 │                 └──────────────┘                 └─────────────┘
└─────────────┘
```

**Setup:**
1. Connect Pi's **WiFi** to your RV's OneControl network
2. Connect Pi's **Ethernet** to your home network (or run HA directly on the Pi)
3. Enable IP forwarding and set up routing/NAT on the Pi
4. Home Assistant can now reach `192.168.1.1` through the Pi

This approach lets Home Assistant stay on your main network while accessing the RV's isolated OneControl system.

### Alternative Options
- Run Home Assistant directly on a Pi connected to RV WiFi
- Use a travel router to bridge networks
- Dual-interface setup on your HA host

## Supported Devices

The integration automatically discovers devices based on their function ID. Common device types include:

### Lights (controllable)
| Function ID | Device Name |
|-------------|-------------|
| 32 | Kitchen Ceiling Light |
| 33 | Kitchen Sconce Light |
| 41 | Living Room Ceiling Light |
| 48 | Porch Light |
| 49 | Awning Light |
| 50 | Outdoor Light |
| 57 | Bedroom Light |
| 63 | Bed Ceiling Light |
| 122 | Scare Light |

### Tanks (sensors)
| Function ID | Device Name |
|-------------|-------------|
| 67 | Fresh Tank |
| 68 | Grey Tank |
| 69 | Black Tank |
| 70 | LP Tank |

### Generator
| Function ID | Device Name |
|-------------|-------------|
| 95 | Generator (control + sensors) |

> **Note:** Device counters (internal IDs) vary per RV installation. The integration uses function IDs to identify device types, then auto-discovers the specific counters for your RV.

## Protocol Details

This integration uses the reverse-engineered Lippert OneControl protocol:
- COBS-encoded frames over TCP
- CRC-8/MAXIM checksums
- TEA cipher authentication for device control

For technical details, see the [OneControl-RV-C-Protocol](https://github.com/manos/OneControl-RV-C-Protocol) repository.

## Safety Notice

⚠️ **This integration controls lights and the generator.** 

The following device types are intentionally **NOT** exposed for safety:
- Water heaters (fire risk if tank is empty)
- Slides (collision risk)
- Awning motor (collision risk)
- Levelers/landing gear (vehicle stability)
- Water pump (dry-run damage)

These may be added in future versions with appropriate safety controls.

## Troubleshooting

### Cannot Connect
- Verify Home Assistant can reach `192.168.1.1` (ping test)
- If using a Pi bridge, ensure the bridge is running and routing is configured
- Check that the controller IP is correct
- Ensure no firewall is blocking port 6969

### Lights Not Responding
- The integration requires a fresh TCP connection for each command
- If commands fail, try again after a few seconds
- The OneControl app should be closed (it may hold the connection)

### Sensors Not Updating
- Tank levels and battery voltage are polled every 30 seconds
- Some sensors require the RV's electrical system to be active

### No Devices Found
- Ensure your RV's OneControl system is powered on
- Try running rediscovery after a few seconds
- Check HA logs for connection errors

## Contributing

Contributions are welcome! Please see the protocol documentation for technical details.

## License

MIT License - see [LICENSE](LICENSE) for details.

---

[releases-shield]: https://img.shields.io/github/release/manos/HomeAssistant-Lippert-OneControl-Integration.svg
[releases]: https://github.com/manos/HomeAssistant-Lippert-OneControl-Integration/releases
[license-shield]: https://img.shields.io/github/license/manos/HomeAssistant-Lippert-OneControl-Integration.svg
