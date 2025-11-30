#!/usr/bin/env python3
"""
Purple Computer WiFi Setup
Simple TUI for connecting to WiFi networks
Uses wpa_supplicant/nmcli depending on what's available
"""

import subprocess
import time
import sys
import getpass
from typing import List, Dict, Optional, Tuple


class WiFiNetwork:
    """Represents a WiFi network"""
    def __init__(self, ssid: str, signal: int, security: str, in_use: bool = False):
        self.ssid = ssid
        self.signal = signal
        self.security = security
        self.in_use = in_use

    def __repr__(self):
        bars = self._signal_bars()
        lock = "🔒" if self.security != "open" else "  "
        active = "●" if self.in_use else " "
        return f"{active} {bars} {lock} {self.ssid}"

    def _signal_bars(self) -> str:
        """Convert signal strength to visual bars"""
        if self.signal >= 75:
            return "▂▄▆█"
        elif self.signal >= 50:
            return "▂▄▆ "
        elif self.signal >= 25:
            return "▂▄  "
        else:
            return "▂   "


class WiFiManager:
    """Manages WiFi connections using available tools"""

    def __init__(self):
        self.use_nmcli = self._check_nmcli()
        if not self.use_nmcli:
            self._check_wpa_supplicant()

    def _check_nmcli(self) -> bool:
        """Check if NetworkManager is available"""
        try:
            result = subprocess.run(
                ['nmcli', '--version'],
                capture_output=True,
                timeout=2
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def _check_wpa_supplicant(self):
        """Check if wpa_supplicant is available"""
        try:
            result = subprocess.run(
                ['which', 'wpa_cli'],
                capture_output=True,
                timeout=2
            )
            if result.returncode != 0:
                print("\n⚠️  Warning: Neither NetworkManager nor wpa_supplicant found")
                print("WiFi setup may not work correctly.\n")
        except subprocess.TimeoutExpired:
            pass

    def scan_networks(self) -> List[WiFiNetwork]:
        """Scan for available WiFi networks"""
        if self.use_nmcli:
            return self._scan_nmcli()
        else:
            return self._scan_wpa()

    def _scan_nmcli(self) -> List[WiFiNetwork]:
        """Scan using NetworkManager"""
        try:
            # Trigger scan
            subprocess.run(['nmcli', 'device', 'wifi', 'rescan'],
                         capture_output=True, timeout=5)
            time.sleep(2)

            # Get results
            result = subprocess.run(
                ['nmcli', '-t', '-f', 'SSID,SIGNAL,SECURITY,IN-USE', 'device', 'wifi', 'list'],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode != 0:
                return []

            networks = []
            seen_ssids = set()

            for line in result.stdout.strip().split('\n'):
                if not line:
                    continue

                parts = line.split(':')
                if len(parts) < 4:
                    continue

                ssid = parts[0]
                if not ssid or ssid in seen_ssids:
                    continue

                seen_ssids.add(ssid)

                try:
                    signal = int(parts[1])
                except ValueError:
                    signal = 0

                security = "secured" if parts[2] else "open"
                in_use = parts[3] == 'yes'

                networks.append(WiFiNetwork(ssid, signal, security, in_use))

            # Sort by signal strength
            networks.sort(key=lambda n: n.signal, reverse=True)
            return networks

        except (subprocess.TimeoutExpired, Exception) as e:
            print(f"Error scanning networks: {e}")
            return []

    def _scan_wpa(self) -> List[WiFiNetwork]:
        """Scan using wpa_supplicant/iw"""
        try:
            # Use iw for scanning if available
            result = subprocess.run(
                ['sudo', 'iw', 'dev'],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode != 0:
                return []

            # Extract interface name
            interface = None
            for line in result.stdout.split('\n'):
                if 'Interface' in line:
                    interface = line.split()[1]
                    break

            if not interface:
                return []

            # Scan
            subprocess.run(
                ['sudo', 'iw', interface, 'scan'],
                capture_output=True,
                timeout=10
            )

            time.sleep(1)

            # Get scan results
            result = subprocess.run(
                ['sudo', 'iw', interface, 'scan'],
                capture_output=True,
                text=True,
                timeout=10
            )

            networks = []
            seen_ssids = set()
            current_ssid = None
            current_signal = 0
            current_security = "open"

            for line in result.stdout.split('\n'):
                line = line.strip()

                if line.startswith('SSID:'):
                    if current_ssid and current_ssid not in seen_ssids:
                        seen_ssids.add(current_ssid)
                        networks.append(WiFiNetwork(
                            current_ssid,
                            current_signal,
                            current_security
                        ))

                    current_ssid = line[5:].strip()
                    current_security = "open"

                elif 'signal:' in line:
                    try:
                        # Extract signal in dBm and convert to percentage
                        signal_dbm = float(line.split()[1])
                        # Convert dBm to rough percentage
                        current_signal = min(100, max(0, int((signal_dbm + 100) * 2)))
                    except (ValueError, IndexError):
                        current_signal = 0

                elif 'WPA' in line or 'RSN' in line:
                    current_security = "secured"

            # Add last network
            if current_ssid and current_ssid not in seen_ssids:
                networks.append(WiFiNetwork(
                    current_ssid,
                    current_signal,
                    current_security
                ))

            networks.sort(key=lambda n: n.signal, reverse=True)
            return networks

        except (subprocess.TimeoutExpired, Exception) as e:
            print(f"Error scanning networks: {e}")
            return []

    def connect(self, ssid: str, password: Optional[str] = None) -> Tuple[bool, str]:
        """Connect to a WiFi network"""
        if self.use_nmcli:
            return self._connect_nmcli(ssid, password)
        else:
            return self._connect_wpa(ssid, password)

    def _connect_nmcli(self, ssid: str, password: Optional[str]) -> Tuple[bool, str]:
        """Connect using NetworkManager"""
        try:
            cmd = ['nmcli', 'device', 'wifi', 'connect', ssid]
            if password:
                cmd.extend(['password', password])

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                return True, f"Connected to {ssid}"
            else:
                error = result.stderr.strip() or result.stdout.strip()
                return False, f"Failed to connect: {error}"

        except subprocess.TimeoutExpired:
            return False, "Connection timeout"
        except Exception as e:
            return False, f"Error: {str(e)}"

    def _connect_wpa(self, ssid: str, password: Optional[str]) -> Tuple[bool, str]:
        """Connect using wpa_supplicant"""
        # This is more complex and requires root - fall back to manual instructions
        return False, (
            f"Please connect manually:\n"
            f"1. sudo nmtui\n"
            f"2. Select 'Activate a connection'\n"
            f"3. Choose '{ssid}' and enter password"
        )

    def get_status(self) -> Optional[Dict]:
        """Get current connection status"""
        if self.use_nmcli:
            return self._status_nmcli()
        else:
            return self._status_wpa()

    def _status_nmcli(self) -> Optional[Dict]:
        """Get status using NetworkManager"""
        try:
            result = subprocess.run(
                ['nmcli', '-t', '-f', 'DEVICE,TYPE,STATE,CONNECTION', 'device'],
                capture_output=True,
                text=True,
                timeout=5
            )

            for line in result.stdout.strip().split('\n'):
                parts = line.split(':')
                if len(parts) >= 4 and parts[1] == 'wifi' and parts[2] == 'connected':
                    return {
                        'interface': parts[0],
                        'ssid': parts[3],
                        'state': 'connected'
                    }

            return None

        except (subprocess.TimeoutExpired, Exception):
            return None

    def _status_wpa(self) -> Optional[Dict]:
        """Get status using wpa_supplicant"""
        # Simplified - just return None for now
        return None


def show_menu():
    """Display the WiFi setup menu"""
    print("\n" + "=" * 50)
    print("     PURPLE COMPUTER - WiFi SETUP")
    print("=" * 50)


def main():
    """Main WiFi setup interface"""
    wifi = WiFiManager()

    show_menu()

    # Show current status
    status = wifi.get_status()
    if status:
        print(f"\n✓ Currently connected to: {status['ssid']}")
    else:
        print("\n○ Not connected to WiFi")

    while True:
        print("\nOptions:")
        print("  1. Scan for networks")
        print("  2. Show current connection")
        print("  3. Exit")

        choice = input("\nChoice (1-3): ").strip()

        if choice == '1':
            print("\n🔍 Scanning for networks...")
            networks = wifi.scan_networks()

            if not networks:
                print("\n⚠️  No networks found")
                print("Make sure WiFi is enabled and try again.")
                continue

            print(f"\nFound {len(networks)} network(s):\n")
            for i, network in enumerate(networks, 1):
                print(f"  {i}. {network}")

            print("\n  0. Cancel")

            try:
                selection = input("\nSelect network (0 to cancel): ").strip()
                if selection == '0' or not selection:
                    continue

                idx = int(selection) - 1
                if idx < 0 or idx >= len(networks):
                    print("Invalid selection")
                    continue

                network = networks[idx]

                # Get password if needed
                password = None
                if network.security != "open":
                    password = getpass.getpass(f"\nPassword for {network.ssid}: ")

                print(f"\nConnecting to {network.ssid}...")
                success, message = wifi.connect(network.ssid, password)

                print(f"\n{message}")

                if success:
                    print("\n✓ WiFi connected successfully!")
                    print("Purple Computer can now check for updates.\n")
                    time.sleep(2)

            except (ValueError, IndexError):
                print("Invalid selection")
            except KeyboardInterrupt:
                print("\n\nCancelled")
                continue

        elif choice == '2':
            status = wifi.get_status()
            if status:
                print(f"\n✓ Connected to: {status['ssid']}")
                print(f"  Interface: {status['interface']}")
            else:
                print("\n○ Not connected")

        elif choice == '3':
            print("\nExiting WiFi setup\n")
            break

        else:
            print("Invalid choice")


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nWiFi setup cancelled\n")
        sys.exit(0)
