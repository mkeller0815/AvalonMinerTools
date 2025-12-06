#!/usr/bin/env python3
"""
Avalon Miner CLI Tool

A command-line interface for interacting with Avalon cryptocurrency miners.
Supports all API commands for monitoring and controlling Avalon miners.

Copyright (c) 2025
SPDX-License-Identifier: Apache-2.0
"""

import sys
import json
import socket
import argparse
import ipaddress
from datetime import datetime
from typing import Dict, Any, Optional


class AvalonMinerAPI:
    """Handle communication with Avalon Miner API"""

    def __init__(self, ip: str, port: int = 4028, timeout: int = 5):
        """
        Initialize API connection parameters

        Args:
            ip: Miner IP address
            port: API port (default: 4028)
            timeout: Socket timeout in seconds (default: 5)
        """
        self.ip = ip
        self.port = port
        self.timeout = timeout
        self._validate_ip()

    def _validate_ip(self):
        """Validate that IP is a valid private network address"""
        try:
            ip_obj = ipaddress.ip_address(self.ip)
            if not ip_obj.is_private:
                raise ValueError(f"IP address {self.ip} is not a private network address")
        except ValueError as e:
            raise ValueError(f"Invalid IP address: {e}")

    def send_command(self, command: str, params: str = '') -> Dict[str, Any]:
        """
        Send a command to the miner API

        Args:
            command: API command name
            params: Optional command parameters

        Returns:
            Dictionary containing the JSON response
        """
        # Build JSON command
        if params:
            json_cmd = json.dumps({
                "command": command,
                "parameter": params
            }, separators=(',', ':'))
        else:
            json_cmd = json.dumps({
                "command": command
            }, separators=(',', ':'))

        try:
            # Create socket connection
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            sock.connect((self.ip, self.port))

            # Send command
            sock.sendall(json_cmd.encode('utf-8'))

            # Small delay to ensure command is processed
            import time
            time.sleep(0.1)

            # Receive response
            response = b''
            while True:
                try:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    response += chunk
                except socket.timeout:
                    break

            sock.close()

            # Parse JSON response (strip null bytes and whitespace)
            response_str = response.decode('utf-8').rstrip('\x00').strip()
            return json.loads(response_str)

        except socket.timeout:
            raise ConnectionError(f"Connection timeout to {self.ip}:{self.port}")
        except socket.error as e:
            raise ConnectionError(f"Socket error: {e}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON response: {e}")
        except Exception as e:
            raise Exception(f"Error communicating with miner: {e}")


def format_hashrate(mhs: float, from_mhs: bool = True) -> str:
    """Format hash rate in human-readable format"""
    if from_mhs:
        ths = mhs / 1_000_000
    else:
        ths = mhs / 1_000
    return f"{ths:.2f} TH/s"


def format_difficulty(diff: float) -> str:
    """Format difficulty with appropriate unit"""
    if diff >= 1e15:
        return f"{diff / 1e15:.2f} P"
    elif diff >= 1e12:
        return f"{diff / 1e12:.2f} T"
    elif diff >= 1e9:
        return f"{diff / 1e9:.2f} G"
    elif diff >= 1e6:
        return f"{diff / 1e6:.2f} M"
    elif diff >= 1e3:
        return f"{diff / 1e3:.2f} K"
    else:
        return f"{diff:.2f}"


def format_uptime(seconds: int) -> str:
    """Format uptime in human-readable format"""
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{days}d {hours}h {minutes}m {secs}s"


def format_timestamp(unix_time: int) -> str:
    """Convert unix timestamp to readable format"""
    return datetime.fromtimestamp(unix_time).strftime('%Y-%m-%d %H:%M:%S')


def parse_estats_field(mm_id0: str, field_name: str) -> str:
    """Parse a field from the MM ID0 string in ESTATS response"""
    import re
    pattern = rf'{field_name}\[([^\]]+)\]'
    match = re.search(pattern, mm_id0)
    return match.group(1) if match else None


def get_work_mode_name(mode_value: str) -> str:
    """Convert work mode number to name"""
    mode_map = {
        '0': 'Eco',
        '1': 'Standard',
        '2': 'Super'
    }
    return mode_map.get(mode_value, f'Unknown ({mode_value})')


def check_status(response: Dict[str, Any]) -> bool:
    """Check if API response indicates success"""
    if 'STATUS' in response and len(response['STATUS']) > 0:
        # STATUS is an array, access first element
        status = response['STATUS'][0] if isinstance(response['STATUS'], list) else response['STATUS']
        status_msg = status.get('Msg', '')
        if 'ASC 0 set OK' in status_msg or 'OK' in status_msg:
            return True
    return False


# Command implementations

def cmd_version(api: AvalonMinerAPI, args) -> None:
    """Get miner version information"""
    response = api.send_command('version')

    if 'VERSION' in response and len(response['VERSION']) > 0:
        ver = response['VERSION'][0]

        print("\n=== Miner Version Information ===")
        print(f"Name             : {ver.get('PROD', 'N/A')}")
        print(f"Model            : {ver.get('MODEL', 'N/A')}")
        print(f"Serial Number    : {ver.get('DNA', 'N/A').upper()}")
        print(f"MAC Address      : {ver.get('MAC', 'N/A')}")
        print(f"\nCGMiner Version  : {ver.get('CGMiner', 'N/A')}")
        print(f"API Version      : {ver.get('API', 'N/A')}")
        print(f"\nFirmware         : {ver.get('LVERSION', ver.get('BVERSION', ver.get('CGVERSION', 'N/A')))}")
        print(f"Hardware Type    : {ver.get('HWTYPE', 'N/A')}")
        print(f"Software Type    : {ver.get('SWTYPE', 'N/A')}")
        print()

    if args.json:
        print(json.dumps(response, indent=2))


def cmd_summary(api: AvalonMinerAPI, args) -> None:
    """Get miner summary statistics"""
    response = api.send_command('summary')

    # Get ESTATS for work mode, power, and uptime info
    estats_response = api.send_command('estats')
    work_mode = None
    power = None
    uptime = None
    if 'STATS' in estats_response and len(estats_response['STATS']) > 0:
        stats = estats_response['STATS'][0] if isinstance(estats_response['STATS'], list) else estats_response['STATS']
        mm_id0 = stats.get('MM ID0', '')
        if mm_id0:
            work_mode_val = parse_estats_field(mm_id0, 'WORKMODE')
            if work_mode_val:
                work_mode = get_work_mode_name(work_mode_val)
            power_val = parse_estats_field(mm_id0, 'MPO')
            if power_val:
                power = f"{power_val}W"

        elapsed = stats.get('Elapsed', 0)
        if elapsed:
            uptime = format_uptime(elapsed)

    # Get LCD for difficulty info
    lcd_response = api.send_command('lcd')
    current_diff = None
    best_diff = None
    if 'LCD' in lcd_response and len(lcd_response['LCD']) > 0:
        lcd = lcd_response['LCD'][0] if isinstance(lcd_response['LCD'], list) else lcd_response['LCD']
        if 'Last Share Difficulty' in lcd:
            current_diff = format_difficulty(lcd['Last Share Difficulty'])
        if 'Best Share' in lcd:
            best_diff = format_difficulty(lcd['Best Share'])

    if 'SUMMARY' in response and len(response['SUMMARY']) > 0:
        summary = response['SUMMARY'][0] if isinstance(response['SUMMARY'], list) else response['SUMMARY']

        print("\n=== Miner Summary ===")
        if uptime:
            print(f"Uptime           : {uptime}")
        if work_mode:
            print(f"Work Mode        : {work_mode}")
        if power:
            print(f"Power Output     : {power}")
        print(f"\nHash Rate (avg)  : {format_hashrate(summary.get('MHS av', 0))}")
        print(f"Hash Rate (5s)   : {format_hashrate(summary.get('MHS 5s', 0))}")
        print(f"Hash Rate (1m)   : {format_hashrate(summary.get('MHS 1m', 0))}")
        print(f"Hash Rate (5m)   : {format_hashrate(summary.get('MHS 5m', 0))}")
        print(f"Hash Rate (15m)  : {format_hashrate(summary.get('MHS 15m', 0))}")
        print(f"\nPool Rejected%   : {summary.get('Pool Rejected%', 0):.4f}%")
        print(f"Pool Stale%      : {summary.get('Pool Stale%', 0):.4f}%")
        if current_diff:
            print(f"\nCurrent Diff     : {current_diff}")
        if best_diff:
            print(f"Best Diff        : {best_diff}")
        print()

    if args.json:
        print(json.dumps(response, indent=2))


def cmd_estats(api: AvalonMinerAPI, args) -> None:
    """Get extended miner statistics"""
    response = api.send_command('estats')

    if args.json:
        print(json.dumps(response, indent=2))
    else:
        print("\n=== Extended Statistics ===")
        print("Note: Use --json flag to see full raw data")
        print("\nResponse received successfully.")
        print("Use 'info' command for parsed miner information.")
        print()


def cmd_lcd(api: AvalonMinerAPI, args) -> None:
    """Get LCD/active pool information"""
    response = api.send_command('lcd')

    if 'LCD' in response and len(response['LCD']) > 0:
        lcd = response['LCD'][0] if isinstance(response['LCD'], list) else response['LCD']

        print("\n=== Active Pool Information ===")
        print(f"Current Pool     : {lcd.get('Current Pool', 'N/A')}")
        print(f"User             : {lcd.get('User', 'N/A')}")

        if 'Last Valid Work' in lcd:
            print(f"Last Valid Work  : {format_timestamp(lcd['Last Valid Work'])}")

        if 'Last Share Difficulty' in lcd:
            print(f"Last Share Diff  : {format_difficulty(lcd['Last Share Difficulty'])}")

        if 'Best Share' in lcd:
            print(f"Best Share       : {format_difficulty(lcd['Best Share'])}")

        print(f"Found Blocks     : {lcd.get('Found Blocks', 0)}")
        print()

    if args.json:
        print(json.dumps(response, indent=2))


def cmd_pools(api: AvalonMinerAPI, args) -> None:
    """Get all pool configurations"""
    response = api.send_command('pools')

    if 'POOLS' in response:
        for pool in response['POOLS']:
            print(f"\n{'='*80}")
            print(f"Pool Index: {pool.get('POOL', 'N/A')}")
            print(f"{'='*80}")
            print(f"URL                     : {pool.get('URL', 'N/A')}")
            print(f"Status                  : {pool.get('Status', 'N/A')}")
            print(f"Priority                : {pool.get('Priority', 'N/A')}")
            print(f"User                    : {pool.get('User', 'N/A')}")
            print(f"\nGetworks                : {pool.get('Getworks', 0)}")
            print(f"Accepted                : {pool.get('Accepted', 0)}")
            print(f"Rejected                : {pool.get('Rejected', 0)}")
            print(f"Stale                   : {pool.get('Stale', 0)}")
            print(f"Discarded               : {pool.get('Discarded', 0)}")
            print(f"Works                   : {pool.get('Works', 0)}")

            if 'Last Share Time' in pool and pool['Last Share Time'] > 0:
                print(f"Last Share Time         : {format_timestamp(pool['Last Share Time'])}")

            print(f"\nHas Stratum             : {pool.get('Has Stratum', False)}")
            print(f"Stratum Active          : {pool.get('Stratum Active', False)}")

            if pool.get('Stratum URL'):
                print(f"Stratum URL             : {pool.get('Stratum URL', 'N/A')}")

            if 'Stratum Difficulty' in pool:
                print(f"Stratum Difficulty      : {format_difficulty(pool['Stratum Difficulty'])}")

            if 'Best Share' in pool:
                print(f"Best Share              : {format_difficulty(pool['Best Share'])}")

            print(f"\nPool Rejected%          : {pool.get('Pool Rejected%', 0):.2f}%")
            print(f"Pool Stale%             : {pool.get('Pool Stale%', 0):.2f}%")
            print(f"Bad Work                : {pool.get('Bad Work', 0)}")
            print(f"Current Block Height    : {pool.get('Current Block Height', 0)}")
        print()

    if args.json:
        print(json.dumps(response, indent=2))


def cmd_info(api: AvalonMinerAPI, args) -> None:
    """Get comprehensive miner information (combines multiple API calls)"""
    print("\nGathering miner information...")

    # Get version info
    ver_response = api.send_command('version')
    ver = ver_response.get('VERSION', [{}])[0]

    # Get LCD info
    lcd_response = api.send_command('lcd')
    lcd_list = lcd_response.get('LCD', [])
    lcd = lcd_list[0] if isinstance(lcd_list, list) and len(lcd_list) > 0 else {}

    # Get summary
    sum_response = api.send_command('summary')
    summary_list = sum_response.get('SUMMARY', [])
    summary = summary_list[0] if isinstance(summary_list, list) and len(summary_list) > 0 else {}

    # Get ESTATS for additional details
    estats_response = api.send_command('estats')
    work_mode = None
    power = None
    temp_max = None
    temp_avg = None
    temp_target = None
    fan_rpm = None
    fan_percent = None
    uptime = None

    if 'STATS' in estats_response and len(estats_response['STATS']) > 0:
        stats = estats_response['STATS'][0] if isinstance(estats_response['STATS'], list) else estats_response['STATS']
        mm_id0 = stats.get('MM ID0', '')
        if mm_id0:
            work_mode_val = parse_estats_field(mm_id0, 'WORKMODE')
            if work_mode_val:
                work_mode = get_work_mode_name(work_mode_val)

            power_val = parse_estats_field(mm_id0, 'MPO')
            if power_val:
                power = f"{power_val}W"

            temp_max_val = parse_estats_field(mm_id0, 'TMax')
            if temp_max_val:
                temp_max = f"{temp_max_val}°C"

            temp_avg_val = parse_estats_field(mm_id0, 'TAvg')
            if temp_avg_val:
                temp_avg = f"{temp_avg_val}°C"

            temp_target_val = parse_estats_field(mm_id0, 'TarT')
            if temp_target_val:
                temp_target = f"{temp_target_val}°C"

            fan_rpm_val = parse_estats_field(mm_id0, 'Fan1')
            if fan_rpm_val:
                fan_rpm = f"{fan_rpm_val} RPM"

            fan_percent_val = parse_estats_field(mm_id0, 'FanR')
            if fan_percent_val:
                fan_percent = fan_percent_val.replace('%', '') + '%'

        elapsed = stats.get('Elapsed', 0)
        if elapsed:
            uptime = format_uptime(elapsed)

    print("\n" + "="*80)
    print("AVALON MINER INFORMATION")
    print("="*80)

    print(f"\nIP Address       : {api.ip}")
    print(f"Model            : {ver.get('MODEL', 'N/A')}")
    print(f"Serial Number    : {ver.get('DNA', 'N/A')}")
    print(f"Firmware         : {ver.get('LVERSION', ver.get('BVERSION', ver.get('CGVERSION', 'N/A')))}")
    if uptime:
        print(f"Uptime           : {uptime}")

    print(f"\n--- Current Settings ---")
    if work_mode:
        print(f"Work Mode        : {work_mode}")
    if power:
        print(f"Power Output     : {power}")
    if temp_max or temp_avg or temp_target:
        print(f"Temperature      : Max={temp_max or 'N/A'}, Avg={temp_avg or 'N/A'}, Target={temp_target or 'N/A'}")
    if fan_rpm or fan_percent:
        print(f"Fan Speed        : {fan_rpm or 'N/A'} ({fan_percent or 'N/A'})")

    print(f"\n--- Hash Rate ---")
    print(f"Average          : {format_hashrate(summary.get('MHS av', 0))}")
    print(f"5 seconds        : {format_hashrate(summary.get('MHS 5s', 0))}")
    print(f"1 minute         : {format_hashrate(summary.get('MHS 1m', 0))}")
    print(f"5 minutes        : {format_hashrate(summary.get('MHS 5m', 0))}")
    print(f"15 minutes       : {format_hashrate(summary.get('MHS 15m', 0))}")

    print(f"\n--- Active Pool ---")
    print(f"Pool             : {lcd.get('Current Pool', 'N/A')}")
    print(f"User             : {lcd.get('User', 'N/A')}")
    if 'Best Share' in lcd:
        print(f"Best Share       : {format_difficulty(lcd['Best Share'])}")
    print(f"Found Blocks     : {lcd.get('Found Blocks', 0)}")

    print(f"\n--- Statistics ---")
    print(f"Rejected%        : {summary.get('Pool Rejected%', 0):.4f}%")
    print(f"Stale%           : {summary.get('Pool Stale%', 0):.4f}%")
    print()


def cmd_set_fan_speed(api: AvalonMinerAPI, args) -> None:
    """Set miner fan speed"""
    if args.auto:
        params = "0,fan-spd,-1"
        mode = "Auto"
    elif args.speed is not None:
        if not 25 <= args.speed <= 100:
            print("Error: Fan speed must be between 25 and 100")
            sys.exit(1)
        params = f"0,fan-spd,{args.speed}"
        mode = f"Exact ({args.speed}%)"
    elif args.min_speed is not None and args.max_speed is not None:
        if not (25 <= args.min_speed <= 100 and 25 <= args.max_speed <= 100):
            print("Error: Fan speeds must be between 25 and 100")
            sys.exit(1)
        if args.min_speed > args.max_speed:
            print("Error: Minimum speed cannot be greater than maximum speed")
            sys.exit(1)
        params = f"0,fan-spd,{args.min_speed}..{args.max_speed}"
        mode = f"Range ({args.min_speed}-{args.max_speed}%)"
    else:
        print("Error: Must specify --auto, --speed, or --min-speed and --max-speed")
        sys.exit(1)

    print(f"\nSetting fan speed to {mode}...")
    response = api.send_command('ascset', params)

    if check_status(response):
        print("Fan speed set successfully")
    else:
        print(f"Command response: {response.get('STATUS', {}).get('Msg', 'Unknown')}")

    if args.json:
        print(json.dumps(response, indent=2))


def cmd_set_work_mode(api: AvalonMinerAPI, args) -> None:
    """Set miner work mode"""
    mode_names = {
        0: "Low/Eco",
        1: "Medium/Standard",
        2: "High/Super"
    }

    if args.mode not in [0, 1, 2]:
        print("Error: Work mode must be 0, 1, or 2")
        sys.exit(1)

    print(f"\nSetting work mode to {args.mode} ({mode_names[args.mode]})...")
    response = api.send_command('ascset', f"0,workmode,set,{args.mode}")

    if check_status(response):
        print("Work mode set successfully")
    else:
        # STATUS is an array, access first element
        status = response.get('STATUS', [{}])[0] if isinstance(response.get('STATUS'), list) else response.get('STATUS', {})
        print(f"Command response: {status.get('Msg', 'Unknown')}")

    if args.json:
        print(json.dumps(response, indent=2))


def cmd_set_target_temp(api: AvalonMinerAPI, args) -> None:
    """Set miner target temperature"""
    if not 50 <= args.temperature <= 90:
        print("Error: Temperature must be between 50 and 90°C")
        sys.exit(1)

    print(f"\nSetting target temperature to {args.temperature}°C...")
    response = api.send_command('ascset', f"0,target-temp,{args.temperature}")

    if check_status(response):
        print("Target temperature set successfully")
        print("\nNote: Temperature will reset to default when miner restarts or work mode changes")
    else:
        print(f"Command response: {response.get('STATUS', {}).get('Msg', 'Unknown')}")

    if args.json:
        print(json.dumps(response, indent=2))


def cmd_get_voltage(api: AvalonMinerAPI, args) -> None:
    """Get miner voltage information"""
    response = api.send_command('ascset', '0,voltage')

    if 'STATUS' in response and len(response['STATUS']) > 0:
        # STATUS is an array, access first element
        status = response['STATUS'][0] if isinstance(response['STATUS'], list) else response['STATUS']
        msg = status.get('Msg', '')
        # Parse voltage string: PS[n0 n1 n2 n3 n4 n5 n6 n7 n8]
        if 'ASC 0 set info:' in msg:
            voltage_str = msg.replace('ASC 0 set info:', '').strip()
            print(f"\n=== Voltage Information ===")
            print(f"Raw String       : {voltage_str}")

            # Try to parse the values
            import re
            matches = re.findall(r'-?\d+', voltage_str)
            if len(matches) >= 7:
                print(f"\nError Code       : {matches[0]}")
                print(f"Reserved 1       : {matches[1]}")
                print(f"Output Voltage   : {matches[2]} (raw units)")
                print(f"Output Current   : {matches[3]} (raw units)")
                print(f"Reserved 2       : {matches[4]}")
                print(f"Commanded Volt.  : {matches[5]} (raw units)")
                print(f"Output Power     : {matches[6]} (raw units)")
                if len(matches) >= 9:
                    print(f"Min Allowed Volt : {matches[7]} (raw units)")
                    print(f"Max Allowed Volt : {matches[8]} (raw units)")
            print()

    if args.json:
        print(json.dumps(response, indent=2))


def cmd_get_fan(api: AvalonMinerAPI, args) -> None:
    """Get current fan speed"""
    response = api.send_command('estats')

    if 'STATS' in response and len(response['STATS']) > 0:
        stats = response['STATS'][0] if isinstance(response['STATS'], list) else response['STATS']
        mm_id0 = stats.get('MM ID0', '')

        if mm_id0:
            fan_rpm = parse_estats_field(mm_id0, 'Fan1')
            fan_percent = parse_estats_field(mm_id0, 'FanR')

            print("\n=== Fan Speed ===")
            if fan_rpm:
                print(f"Fan Speed (RPM)  : {fan_rpm}")
            if fan_percent:
                print(f"Fan Speed (%)    : {fan_percent}")
            print()
        else:
            print("Error: Could not retrieve fan information")

    if args.json:
        print(json.dumps(response, indent=2))


def cmd_get_work_mode(api: AvalonMinerAPI, args) -> None:
    """Get current work mode"""
    response = api.send_command('estats')

    if 'STATS' in response and len(response['STATS']) > 0:
        stats = response['STATS'][0] if isinstance(response['STATS'], list) else response['STATS']
        mm_id0 = stats.get('MM ID0', '')

        if mm_id0:
            work_mode_val = parse_estats_field(mm_id0, 'WORKMODE')

            print("\n=== Work Mode ===")
            if work_mode_val:
                work_mode = get_work_mode_name(work_mode_val)
                print(f"Current Mode     : {work_mode} (Mode {work_mode_val})")
            else:
                print("Error: Could not retrieve work mode")
            print()
        else:
            print("Error: Could not retrieve work mode information")

    if args.json:
        print(json.dumps(response, indent=2))


def cmd_get_target_temp(api: AvalonMinerAPI, args) -> None:
    """Get current target temperature"""
    response = api.send_command('estats')

    if 'STATS' in response and len(response['STATS']) > 0:
        stats = response['STATS'][0] if isinstance(response['STATS'], list) else response['STATS']
        mm_id0 = stats.get('MM ID0', '')

        if mm_id0:
            target_temp = parse_estats_field(mm_id0, 'TarT')
            temp_max = parse_estats_field(mm_id0, 'TMax')
            temp_avg = parse_estats_field(mm_id0, 'TAvg')

            print("\n=== Temperature Settings ===")
            if target_temp:
                print(f"Target Temp      : {target_temp}°C")
            if temp_max:
                print(f"Current Max      : {temp_max}°C")
            if temp_avg:
                print(f"Current Avg      : {temp_avg}°C")
            print()
        else:
            print("Error: Could not retrieve temperature information")

    if args.json:
        print(json.dumps(response, indent=2))


def cmd_set_voltage(api: AvalonMinerAPI, args) -> None:
    """Set miner voltage"""
    print(f"\nSetting voltage to {args.voltage}...")
    print("WARNING: Setting incorrect voltage can damage your miner!")

    if not args.force:
        confirm = input("Are you sure you want to proceed? (yes/no): ")
        if confirm.lower() != 'yes':
            print("Operation cancelled")
            return

    response = api.send_command('ascset', f'0,voltage,{args.voltage}')

    if check_status(response):
        print("Voltage set successfully")
    else:
        print(f"Command response: {response.get('STATUS', {}).get('Msg', 'Unknown')}")

    if args.json:
        print(json.dumps(response, indent=2))


def cmd_reboot(api: AvalonMinerAPI, args) -> None:
    """Reboot the miner"""
    if not 0 <= args.delay <= 300:
        print("Error: Delay must be between 0 and 300 seconds")
        sys.exit(1)

    if args.delay > 0:
        print(f"\nScheduling reboot in {args.delay} seconds...")
    else:
        print("\nRebooting miner immediately...")

    if not args.force:
        confirm = input("Are you sure you want to reboot the miner? (yes/no): ")
        if confirm.lower() != 'yes':
            print("Operation cancelled")
            return

    response = api.send_command('ascset', f'0,reboot,{args.delay}')

    if check_status(response):
        print("Reboot command sent successfully")
    else:
        print(f"Command response: {response.get('STATUS', {}).get('Msg', 'Unknown')}")

    if args.json:
        print(json.dumps(response, indent=2))


def cmd_reset_filter_clean(api: AvalonMinerAPI, args) -> None:
    """Reset filter clean reminder"""
    print("\nResetting filter clean reminder...")
    response = api.send_command('ascset', '0,filter-clean,1')

    if check_status(response):
        print("Filter clean reminder reset successfully")
    else:
        print(f"Command response: {response.get('STATUS', {}).get('Msg', 'Unknown')}")

    if args.json:
        print(json.dumps(response, indent=2))


def cmd_set_pool(api: AvalonMinerAPI, args) -> None:
    """Configure a mining pool"""
    if not 0 <= args.pool_id <= 2:
        print("Error: Pool ID must be 0, 1, or 2")
        sys.exit(1)

    print(f"\nConfiguring pool {args.pool_id}...")
    params = f"admin,{args.password},{args.pool_id},{args.url},{args.username},{args.pool_password}"

    response = api.send_command('setpool', params)

    if 'STATUS' in response and len(response['STATUS']) > 0:
        status = response['STATUS'][0] if isinstance(response['STATUS'], list) else response['STATUS']
        print(f"Response: {status.get('Msg', 'Unknown')}")

    if args.json:
        print(json.dumps(response, indent=2))


def cmd_enable_pool(api: AvalonMinerAPI, args) -> None:
    """Enable a mining pool"""
    if not 0 <= args.pool_id <= 2:
        print("Error: Pool ID must be 0, 1, or 2")
        sys.exit(1)

    print(f"\nEnabling pool {args.pool_id}...")
    response = api.send_command('enablepool', str(args.pool_id))

    if 'STATUS' in response and len(response['STATUS']) > 0:
        status = response['STATUS'][0] if isinstance(response['STATUS'], list) else response['STATUS']
        print(f"Response: {status.get('Msg', 'Unknown')}")

    if args.json:
        print(json.dumps(response, indent=2))


def cmd_disable_pool(api: AvalonMinerAPI, args) -> None:
    """Disable a mining pool"""
    if not 0 <= args.pool_id <= 2:
        print("Error: Pool ID must be 0, 1, or 2")
        sys.exit(1)

    print(f"\nDisabling pool {args.pool_id}...")
    response = api.send_command('disablepool', str(args.pool_id))

    if 'STATUS' in response and len(response['STATUS']) > 0:
        status = response['STATUS'][0] if isinstance(response['STATUS'], list) else response['STATUS']
        print(f"Response: {status.get('Msg', 'Unknown')}")

    if args.json:
        print(json.dumps(response, indent=2))


def cmd_switch_pool(api: AvalonMinerAPI, args) -> None:
    """Switch to a different pool"""
    if not 0 <= args.pool_id <= 2:
        print("Error: Pool ID must be 0, 1, or 2")
        sys.exit(1)

    print(f"\nSwitching to pool {args.pool_id}...")
    response = api.send_command('switchpool', str(args.pool_id))

    if 'STATUS' in response and len(response['STATUS']) > 0:
        status = response['STATUS'][0] if isinstance(response['STATUS'], list) else response['STATUS']
        print(f"Response: {status.get('Msg', 'Unknown')}")

    if args.json:
        print(json.dumps(response, indent=2))


def cmd_set_pool_priority(api: AvalonMinerAPI, args) -> None:
    """Set pool priority order"""
    # Validate priority format
    priorities = args.priority.split(',')
    if not all(p.strip() in ['0', '1', '2'] for p in priorities):
        print("Error: Priority must be comma-separated pool IDs (0, 1, 2)")
        sys.exit(1)

    print(f"\nSetting pool priority to: {args.priority}")
    response = api.send_command('poolpriority', args.priority)

    if 'STATUS' in response and len(response['STATUS']) > 0:
        status = response['STATUS'][0] if isinstance(response['STATUS'], list) else response['STATUS']
        print(f"Response: {status.get('Msg', 'Unknown')}")

    if args.json:
        print(json.dumps(response, indent=2))


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Avalon Miner CLI - Control and monitor Avalon cryptocurrency miners',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Get miner information
  %(prog)s 192.168.1.100 info
  %(prog)s 192.168.1.100 version

  # Set fan speed
  %(prog)s 192.168.1.100 set-fan --auto
  %(prog)s 192.168.1.100 set-fan --speed 80
  %(prog)s 192.168.1.100 set-fan --min-speed 30 --max-speed 100

  # Set work mode
  %(prog)s 192.168.1.100 set-work-mode --mode 1

  # Manage pools
  %(prog)s 192.168.1.100 pools
  %(prog)s 192.168.1.100 switch-pool --pool-id 1
        """
    )

    parser.add_argument('ip', help='Miner IP address')
    parser.add_argument('--port', type=int, default=4028, help='API port (default: 4028)')
    parser.add_argument('--timeout', type=int, default=5, help='Connection timeout in seconds (default: 5)')

    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    subparsers.required = True

    # Information commands
    version_parser = subparsers.add_parser('version', help='Get miner version information')
    version_parser.add_argument('--json', action='store_true', help='Output raw JSON response')

    summary_parser = subparsers.add_parser('summary', help='Get miner summary statistics')
    summary_parser.add_argument('--json', action='store_true', help='Output raw JSON response')

    estats_parser = subparsers.add_parser('estats', help='Get extended statistics')
    estats_parser.add_argument('--json', action='store_true', help='Output raw JSON response')

    lcd_parser = subparsers.add_parser('lcd', help='Get LCD/active pool information')
    lcd_parser.add_argument('--json', action='store_true', help='Output raw JSON response')

    pools_parser = subparsers.add_parser('pools', help='Get all pool configurations')
    pools_parser.add_argument('--json', action='store_true', help='Output raw JSON response')

    info_parser = subparsers.add_parser('info', help='Get comprehensive miner info (combines multiple calls)')

    # Fan speed control
    fan_parser = subparsers.add_parser('set-fan', help='Set fan speed')
    fan_group = fan_parser.add_mutually_exclusive_group(required=True)
    fan_group.add_argument('--auto', action='store_true', help='Enable automatic fan control')
    fan_group.add_argument('--speed', type=int, metavar='PCT', help='Set exact fan speed (25-100%%)')
    fan_parser.add_argument('--min-speed', type=int, metavar='PCT', help='Set minimum fan speed (25-100%%) - use with --max-speed')
    fan_parser.add_argument('--max-speed', type=int, metavar='PCT', help='Set maximum fan speed (25-100%%) - use with --min-speed')
    fan_parser.add_argument('--json', action='store_true', help='Output raw JSON response')

    # Work mode
    work_parser = subparsers.add_parser('set-work-mode', help='Set work mode (0=Low/Eco, 1=Medium/Standard, 2=High/Super)')
    work_parser.add_argument('--mode', type=int, required=True, choices=[0, 1, 2],
                            help='Work mode: 0=Low/Eco, 1=Medium/Standard, 2=High/Super')
    work_parser.add_argument('--json', action='store_true', help='Output raw JSON response')

    # Target temperature
    temp_parser = subparsers.add_parser('set-target-temp', help='Set target ASIC temperature')
    temp_parser.add_argument('--temperature', type=int, required=True, metavar='CELSIUS',
                            help='Target temperature in Celsius (50-90)')
    temp_parser.add_argument('--json', action='store_true', help='Output raw JSON response')

    # Voltage
    get_volt_parser = subparsers.add_parser('get-voltage', help='Get voltage information')
    get_volt_parser.add_argument('--json', action='store_true', help='Output raw JSON response')

    # Get fan speed
    get_fan_parser = subparsers.add_parser('get-fan', help='Get current fan speed')
    get_fan_parser.add_argument('--json', action='store_true', help='Output raw JSON response')

    # Get work mode
    get_work_mode_parser = subparsers.add_parser('get-work-mode', help='Get current work mode')
    get_work_mode_parser.add_argument('--json', action='store_true', help='Output raw JSON response')

    # Get target temperature
    get_target_temp_parser = subparsers.add_parser('get-target-temp', help='Get current target temperature')
    get_target_temp_parser.add_argument('--json', action='store_true', help='Output raw JSON response')

    set_volt_parser = subparsers.add_parser('set-voltage', help='Set voltage (DANGEROUS - use with caution!)')
    set_volt_parser.add_argument('--voltage', type=int, required=True, metavar='VALUE',
                                help='Voltage value (device-specific units)')
    set_volt_parser.add_argument('--force', action='store_true', help='Skip confirmation prompt')
    set_volt_parser.add_argument('--json', action='store_true', help='Output raw JSON response')

    # Reboot
    reboot_parser = subparsers.add_parser('reboot', help='Reboot the miner')
    reboot_parser.add_argument('--delay', type=int, default=0, metavar='SECONDS',
                              help='Delay before reboot in seconds (0-300, default: 0)')
    reboot_parser.add_argument('--force', action='store_true', help='Skip confirmation prompt')
    reboot_parser.add_argument('--json', action='store_true', help='Output raw JSON response')

    # Filter clean
    filter_parser = subparsers.add_parser('reset-filter-clean', help='Reset filter clean reminder')
    filter_parser.add_argument('--json', action='store_true', help='Output raw JSON response')

    # Pool configuration
    setpool_parser = subparsers.add_parser('set-pool', help='Configure a mining pool (requires authentication)')
    setpool_parser.add_argument('--pool-id', type=int, required=True, choices=[0, 1, 2],
                               help='Pool ID to configure (0, 1, or 2)')
    setpool_parser.add_argument('--url', required=True, help='Pool URL (e.g., stratum+tcp://pool.example.com:3333)')
    setpool_parser.add_argument('--username', required=True, help='Pool username/worker name')
    setpool_parser.add_argument('--pool-password', required=True, help='Pool password (use "x" if not required)')
    setpool_parser.add_argument('--password', required=True, help='Miner admin password')
    setpool_parser.add_argument('--json', action='store_true', help='Output raw JSON response')

    # Pool management
    enable_pool_parser = subparsers.add_parser('enable-pool', help='Enable a mining pool')
    enable_pool_parser.add_argument('--pool-id', type=int, required=True, choices=[0, 1, 2],
                                   help='Pool ID to enable (0, 1, or 2)')
    enable_pool_parser.add_argument('--json', action='store_true', help='Output raw JSON response')

    disable_pool_parser = subparsers.add_parser('disable-pool', help='Disable a mining pool')
    disable_pool_parser.add_argument('--pool-id', type=int, required=True, choices=[0, 1, 2],
                                    help='Pool ID to disable (0, 1, or 2)')
    disable_pool_parser.add_argument('--json', action='store_true', help='Output raw JSON response')

    switch_pool_parser = subparsers.add_parser('switch-pool', help='Switch to a different active pool')
    switch_pool_parser.add_argument('--pool-id', type=int, required=True, choices=[0, 1, 2],
                                   help='Pool ID to switch to (0, 1, or 2)')
    switch_pool_parser.add_argument('--json', action='store_true', help='Output raw JSON response')

    priority_parser = subparsers.add_parser('set-pool-priority', help='Set pool priority order')
    priority_parser.add_argument('--priority', required=True, metavar='LIST',
                                help='Comma-separated pool priority (e.g., "1,0" or "0,1,2")')
    priority_parser.add_argument('--json', action='store_true', help='Output raw JSON response')

    args = parser.parse_args()

    # Create API instance
    try:
        api = AvalonMinerAPI(args.ip, args.port, args.timeout)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Execute command
    try:
        command_map = {
            'version': cmd_version,
            'summary': cmd_summary,
            'estats': cmd_estats,
            'lcd': cmd_lcd,
            'pools': cmd_pools,
            'info': cmd_info,
            'set-fan': cmd_set_fan_speed,
            'get-fan': cmd_get_fan,
            'set-work-mode': cmd_set_work_mode,
            'get-work-mode': cmd_get_work_mode,
            'set-target-temp': cmd_set_target_temp,
            'get-target-temp': cmd_get_target_temp,
            'get-voltage': cmd_get_voltage,
            'set-voltage': cmd_set_voltage,
            'reboot': cmd_reboot,
            'reset-filter-clean': cmd_reset_filter_clean,
            'set-pool': cmd_set_pool,
            'enable-pool': cmd_enable_pool,
            'disable-pool': cmd_disable_pool,
            'switch-pool': cmd_switch_pool,
            'set-pool-priority': cmd_set_pool_priority,
        }

        command_map[args.command](api, args)

    except ConnectionError as e:
        print(f"Connection Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
