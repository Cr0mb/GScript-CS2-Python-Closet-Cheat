<img width="1600" height="900" alt="image" src="https://github.com/user-attachments/assets/ebb3f237-6b6b-4c07-847d-ceb908f579ce" />

# GScript

> Free, open-source Counter-Strike 2 external cheat with user-mode memory access.

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

> No cheat is 100% undetected. Use responsibly.
