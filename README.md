# Home Assistant Lippert OneControl Integration

[![GitHub Release][releases-shield]][releases]
[![License][license-shield]](LICENSE)

Control your RV's Lippert OneControl system directly from Home Assistant!

## Features

- **💡 Light Control**: Turn RV lights ON/OFF
  - Ceiling lights, porch lights, awning lights, scare lights, and more
  - Automatic discovery of installed lights
  - Real-time state sync from broadcasts

- **📊 Tank Sensors**: Monitor tank levels
  - Fresh Water
  - Grey Water
  - Black Water
  - LP Gas (Propane)

- **🔋 Battery Voltage**: Real-time battery monitoring

- **⚡ Generator Control**: Start/stop your generator
  - Power switch (ON/OFF)
  - State monitoring (Off, Priming, Starting, Running, Stopping)
  - Hour meter tracking

- **🔥 Water Heaters**: Control gas and electric water heaters
  - Gas Water Heater (ON/OFF)
  - Electric Water Heater (ON/OFF)
  - Real-time state sync from broadcasts

- **💧 Water Pump**: Control your RV's water pump
  - ON/OFF control
  - Real-time state sync from broadcasts

- **🔄 Auto-Discovery**: Automatically finds devices installed in your RV
  - No manual configuration of device IDs needed
  - Device selection UI during setup - choose which devices to add
  - Rediscover devices anytime via Configure menu
  - Existing devices preserved when rediscovering

- **📡 Real-Time State Sync**: Device states update automatically
  - Lights, water heaters, and water pump sync from OneControl broadcasts
  - ~7 second polling interval for fast state updates
  - Changes from the OneControl app reflect in Home Assistant

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
6. Select which devices you want to add (all are selected by default)

### Rediscovering Devices

If you add new devices to your RV or update the integration:

1. Go to **Settings → Devices & Services → Integrations**
2. Find **Lippert OneControl** → click **Configure**
3. Select **🔄 Rediscover Devices**
4. New devices will be shown for selection
5. Your existing devices and dashboard configurations are preserved

### Viewing Current Devices

1. Go to **Settings → Devices & Services → Integrations**
2. Find **Lippert OneControl** → click **Configure**
3. Select **📋 View Current Devices**

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
| 58 | Living Room Light |
| 59 | Kitchen Light |
| 63 | Bed Ceiling Light |
| 122 | Scare Light |

### Tanks (sensors)
| Function ID | Device Name |
|-------------|-------------|
| 67 | Fresh Tank |
| 68 | Grey Tank |
| 69 | Black Tank |
| 70 | LP Tank |
| 176 | LP Tank (alternate) |

### Water Heaters (controllable)
| Function ID | Device Name |
|-------------|-------------|
| 3 | Gas Water Heater |
| 4 | Electric Water Heater |

### Water Pump (controllable)
| Function ID | Device Name |
|-------------|-------------|
| 5 | Water Pump |

### Generator (controllable + sensors)
| Function ID | Device Name |
|-------------|-------------|
| 95 | Generator |

> **Note:** Device counters (internal IDs) vary per RV installation. The integration uses function IDs to identify device types, then auto-discovers the specific counters for your RV.

## Protocol Details

This integration uses the reverse-engineered Lippert OneControl protocol:
- COBS-encoded frames over TCP
- CRC-8/MAXIM checksums
- TEA cipher authentication for device control
- RelayBasicLatchingStatus2 broadcasts for state synchronization

For technical details, see the [OneControl-RV-C-Protocol](https://github.com/manos/OneControl-RV-C-Protocol) repository.

## Safety Notice

⚠️ **Use at your own risk.** This integration controls electrical systems in your RV.

The following device types are intentionally **NOT** exposed:
- **Slides** - Collision/pinch risk, requires visual confirmation
- **Awning motor** - Collision risk, requires visual confirmation  
- **Levelers/landing gear** - Vehicle stability risk

These require physical observation during operation and are not suitable for remote control.

## Troubleshooting

### Cannot Connect
- Verify Home Assistant can reach `192.168.1.1` (ping test)
- If using a Pi bridge, ensure the bridge is running and routing is configured
- Check that the controller IP is correct
- Ensure no firewall is blocking port 6969

### Lights/Switches Not Responding
- The integration uses automatic retry (2 attempts) for commands
- If commands fail, try again after a few seconds
- The OneControl app should be closed (it may hold the connection)

### State Shows Incorrect Value
- Device states sync from broadcasts every ~7 seconds
- Toggle the device from OneControl app and wait for HA to update
- If state is stuck, restart Home Assistant

### Sensors Not Updating
- Tank levels and battery voltage are polled every 7 seconds
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
