import requests
import re
import logging
from bs4 import BeautifulSoup

_LOGGER = logging.getLogger(__name__)
REQUEST_TIMEOUT = 10

# TP-Link Status Mappings
TPstate = {0: 'Disabled', 1: 'Enabled'}
TPlinkStatus = {
    0: "Link Down", 2: "10M Half", 3: "10M Full",
    5: "100M Full", 6: "1000M Full"
}

def fetch_port_statistics(ip, username, password):
    """Fetch and parse port statistics from TP-Link switch web interface."""
    session = requests.Session()
    data = {"logon": "Login", "username": username, "password": password}
    try:
        # Login to the switch
        response = session.post(f"http://{ip}/logon.cgi", data=data, timeout=REQUEST_TIMEOUT)
        if response.status_code != 200:
            _LOGGER.error("Login failed! Check username and password.")
            return None

        # Get port statistics page
        response = session.get(f"http://{ip}/PortStatisticsRpm.htm", timeout=REQUEST_TIMEOUT)
        if response.status_code != 200:
            _LOGGER.error("Failed to fetch PortStatisticsRpm.htm")
            return None

        soup = BeautifulSoup(response.text, "html.parser")

        # Extract JavaScript block containing port statistics
        script_text = soup.find("script")
        if not script_text:
            _LOGGER.error("No script block found in the HTML!")
            return None
        script_text = script_text.string

        # Extract 'pkts' array
        pkts_match = re.search(r"pkts:\[(.*?)\]", script_text)
        if not pkts_match:
            _LOGGER.error("No packet data found!")
            return None
        pkts_values = list(map(int, pkts_match.group(1).split(",")))

        # Extract Port Status (Enabled/Disabled)
        state_match = re.search(r"state:\[(.*?)\]", script_text)
        state_values = list(map(int, state_match.group(1).split(",")))

        # Extract Link Status (Speed or Link Down)
        link_match = re.search(r"link_status:\[(.*?)\]", script_text)
        link_values = list(map(int, link_match.group(1).split(",")))

        # Extract Number of Ports
        max_port_num_match = re.search(r"var max_port_num = (\d+);", script_text)
        if not max_port_num_match:
            _LOGGER.error("Could not find max_port_num!")
            return None
        max_port_num = int(max_port_num_match.group(1))

        # Organize Data by Port
        port_stats = {}
        for i in range(max_port_num):
            port_stats[i + 1] = {
                "state": TPstate.get(state_values[i], "Unknown"),
                "link_status": TPlinkStatus.get(link_values[i], "Unknown"),
                "tx_good": pkts_values[i * 4],
                "tx_bad": pkts_values[i * 4 + 1],
                "rx_good": pkts_values[i * 4 + 2],
                "rx_bad": pkts_values[i * 4 + 3]
            }

        return port_stats
    except requests.Timeout:
        _LOGGER.warning(
            "Timeout fetching port statistics from %s after %ss",
            ip,
            REQUEST_TIMEOUT,
        )
        return None
    except requests.RequestException as err:
        _LOGGER.error("Network error fetching port statistics from %s: %s", ip, err)
        return None

def fetch_system_info(ip, username, password):
    """Fetch system info from the TP-Link switch web interface."""
    session = requests.Session()
    data = {"logon": "Login", "username": username, "password": password}

    try:
        # Login to the switch
        login_response = session.post(
            f"http://{ip}/logon.cgi",
            data=data,
            timeout=REQUEST_TIMEOUT,
        )
        if login_response.status_code != 200:
            _LOGGER.error(f"Login failed during system info fetch: {login_response.status_code}")
            return None
        
        # Get system info page
        response = session.get(f"http://{ip}/SystemInfoRpm.htm", timeout=REQUEST_TIMEOUT)
        
        if response.status_code != 200:
            _LOGGER.error(f"Failed to fetch system info (HTTP {response.status_code})")
            return None

        soup = BeautifulSoup(response.text, "html.parser")

        # Extract JavaScript block containing system info
        script_tag = soup.find("script")
        if not script_tag or not script_tag.string:
            _LOGGER.error("No script block found in SystemInfoRpm.htm")
            return None

        script_text = script_tag.string

        # Debug: Log script text
        _LOGGER.debug("System Info Script Block retrieved")

        # Extract system info safely
        def extract_value(pattern):
            match = re.search(pattern, script_text, re.DOTALL)  # Use DOTALL to match across lines
            return match.group(1).strip() if match else "Unknown"

        info = {
            "device_model": extract_value(r'descriStr:\[\s*"([^"]+)"\s*\]'),
            "mac_address": extract_value(r'macStr:\[\s*"([^"]+)"\s*\]'),
            "ip_address": extract_value(r'ipStr:\[\s*"([^"]+)"\s*\]'),
            "subnet_mask": extract_value(r'netmaskStr:\[\s*"([^"]+)"\s*\]'),
            "default_gateway": extract_value(r'gatewayStr:\[\s*"([^"]+)"\s*\]'),
            "firmware_version": extract_value(r'firmwareStr:\[\s*"([^"]+)"\s*\]'),
            "hardware_version": extract_value(r'hardwareStr:\[\s*"([^"]+)"\s*\]')
        }

        # Verify we extracted a valid MAC address 
        if info["mac_address"] == "Unknown":
            _LOGGER.error("Failed to extract MAC address from system info")
            return None

        return info
    except requests.Timeout:
        _LOGGER.warning(
            "Timeout fetching system info from %s after %ss",
            ip,
            REQUEST_TIMEOUT,
        )
        return None
    except requests.RequestException as e:
        _LOGGER.error(f"Network error in fetch_system_info: {str(e)}")
        return None
    except Exception as e:
        _LOGGER.error(f"Exception in fetch_system_info: {str(e)}")
        return None
