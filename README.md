# 5-Axis Trapdoor Logger Application

This is essentially a logger application for the TDS530.  
It is a project created using `uv`. We recommend using `uv` for package management.  
`conda` is the next best option. Using the system `pip` directly is strongly discouraged.  
It receives and displays data from the TDS530 in real time over TCP in a PyWebView-based native window.  
File saving can be controlled from the UI.

## How to Run
1. Set up the `uv` environment and activate the virtual environment (`venv`).
2. Install the dependencies.
3. Run `main.py`.
4. A native window will open and the data monitor will be displayed.
5. Close the window when measurement is finished.

## Default Connection Settings
- TDS530 IP address: "192.168.100.100"  
    Change this only if you understand what you are doing.
- TDS530 port number: 4242  
    This cannot be changed due to device constraints.

## Connection Method
- Connect the TDS530 LAN port directly to the computer's wired LAN port with a LAN cable.
- Be sure to use a crossover cable.
- If you use a hub, a straight-through cable can also work, but only use a hub if you understand what you are doing.

## TDS530 Settings
- Set the output destination to "Output to LAN".
- Set the "IP Address" to "192.168.100.100".
- Set the "Network Mask" to "255.255.255.0".
- Set the "Port Number" to "4242".
- Do not set a "Gateway".
- If you use a hub, a straight-through cable can also work, but only change these settings freely if you understand what you are doing.

## Computer Settings
- Set the computer's wired LAN "IP Address" to "192.168.100.x" (where x is any number from 1 to 254 except 100).
- Set the computer's wired LAN "Subnet Mask" to "255.255.255.0".
- Do not set a "Gateway" for the computer's wired LAN.
- If you use a hub, a straight-through cable can also work, but only change these settings freely if you understand what you are doing.

## Notes
- As of December 2025, the only dependency we are aware of is `pywebview`. However, this may change depending on Python or pywebview updates.
