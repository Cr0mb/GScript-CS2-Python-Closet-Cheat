# GScript

> Free, open-source Counter-Strike 2 external cheat with user-mode memory access.

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Platform](https://img.shields.io/badge/Platform-Windows%2010%2F11-lightgrey.svg)]()
[![License](https://img.shields.io/badge/License-MIT-green.svg)]()
[![Game](https://img.shields.io/badge/Game-CS2-orange.svg)]()

---

## Disclaimer

**This software is for EDUCATIONAL PURPOSES ONLY.** 

- Use at your own risk
- The authors are not responsible for any bans or consequences
- Do not use on FaceIT, ESEA, or other competitive platforms
- This is an external overlay - does not inject into game process

---

## Features

### Aimbot
- Configurable Field of View (FOV)
- Recoil Control System (RCS)
- Smoothness adjustment
- Target bone selection (Head, Neck, Chest, Pelvis, etc.)
- Dynamic FOV (distance-based scaling)
- Closest to crosshair mode
- Visual FOV circle
- Custom aim key bind

### ESP (Player)
- Box ESP
- Health bars
- Skeleton ESP (visible/occluded colors)
- Player names
- Weapon name display
- Money display
- Flash indicator
- Scope indicator
- Visible-only mode
- Team filters (T / CT)

### ESP (World)
- Map status display
- Team list
- Spectator list
- External crosshair (customizable size/thickness)
- FPS overlay
- Hide from screen capture option

### Triggerbot
- Custom trigger key
- Always-on mode
- Configurable cooldown
- Shoot teammates toggle

### Misc
- Bunny Hop (BHop)
- 2D Radar (customizable FPS, size, position, range)
- Visibility checks (ESP & Aimbot)
- Current map detection

### Customization
- Full color customization for all ESP elements
- Team-specific colors
- Visible/occluded color options
- Multiple color presets
- Configurable menu theme

### System
- Save/Load/Reset configurations
- Panic key (instant unload)
- **User-mode only** (no kernel driver required)
- Low detection risk
- Auto-offset scanning

---

## Installation

### Requirements
- **OS:** Windows 10/11 (x64)
- **Python:** 3.10 or higher
- **Game:** Counter-Strike 2

### Setup

1. **Install Python** from [python.org](https://www.python.org/downloads/)

2. **Install dependencies:**
   ```bash
   pip install PyQt5 pywin32
   ```

3. **Clone or download this repository:**
   ```bash
   git clone https://github.com/Cr0mb/GScript.git
   cd GScript
   ```

4. **Run the loader:**
   ```bash
   python Loader.py
   ```

5. **Launch Counter-Strike 2**

6. **Press INSERT in-game** to open the menu

---

## Controls

| Key | Action |
|-----|--------|
| `INSERT` | Toggle menu |
| `DELETE` | Panic key (unload all features) |
| `Mouse` | Navigate menu / Drag window |

---

## Project Structure

```
GScript/
├── GScript.py                 # Main entry point
├── Loader.py                  # License/loader UI
├── vischeck.pyd               # Compiled visibility check module
├── Features/
│   ├── aimbot.py              # Aimbot (RCS) feature
│   ├── bhop.py                # Bunny hop feature
│   ├── esp.py                 # ESP/wallhack feature
│   ├── radar.py               # 2D radar feature
│   └── triggerbot.py          # Triggerbot feature
├── Process/
│   ├── config.py              # Configuration settings
│   ├── helpers.py             # Memory reading, overlay, process utilities
│   ├── offset_manager.py      # Offset scanning and management
│   ├── offsets.py             # Game offset definitions
│   └── qt_overlay.py          # PyQt5 overlay rendering
└── logs/                      # Runtime logs (created at runtime)
```

---

## Configuration

Configs are stored in `config/` directory as JSON files.

### In-Menu Config Management
- **SAVE** - Save current settings
- **LOAD** - Load saved settings
- **RESET** - Restore defaults

Config location: `%APPDATA%\GScript\gscript_config.json`

---

## Troubleshooting

### Menu not showing?
- Press `INSERT` key
- Ensure CS2 is running before launching
- Check if Python has overlay permissions

### ESP not working?
- Offsets are auto-scanned on startup
- Ensure you're in a match (not main menu)
- Check visibility settings in menu

### Python errors?
- Verify Python 3.10+ is installed
- Reinstall dependencies: `pip install --force-reinstall PyQt5 pywin32`
- Run as administrator if needed

### Crashes on startup?
- Disable antivirus temporarily
- Run as administrator
- Check Windows Event Viewer for details

---

## Safety

### Why User-Mode?
- **Lower detection risk** - No kernel driver signature
- **No admin required** - Runs with standard permissions
- **Simpler setup** - No driver installation
- **Portable** - Works on any Windows 10/11 system

### Detection Risk
| Feature | Risk Level |
|---------|------------|
| User-mode memory read | Low |
| External overlay | Low |
| Offset scanning | Low |
| **Overall** | **Low-Medium** |

> No cheat is 100% undetected. Use responsibly.

---

## Development

### Building from Source

No build process required - runs directly from Python source.

### Adding Features

1. Create new feature in `Features/` directory
2. Import in `GScript.py` `_lazy_import_features()`
3. Add menu options in `TABS` list
4. Add config options in `Process/config.py`

### Code Style
- Python 3.10+ syntax
- Type hints where applicable
- Minimal comments (self-documenting code)
- No kernel drivers

---

## License

This project is provided as-is for educational purposes.

---

## Credits

- **Developer:** Cr0mb
- **Inspired by:** Various open-source CS2 projects
- **Special thanks:** UnknownCheats community

---

## Support

- **GitHub Issues:** For bug reports and feature requests
- **UnknownCheats:** Release thread for discussion

---

## Star History

If you find this project useful, please consider giving it a star!

---

<div align="center">

**Made by [Cr0mb](https://github.com/Cr0mb)**

*Use responsibly. Don't ruin the game for others.*

</div>
