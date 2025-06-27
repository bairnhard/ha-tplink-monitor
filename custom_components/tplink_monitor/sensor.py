import logging
import asyncio
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
from datetime import timedelta
from .const import DOMAIN, CONF_IP, CONF_USERNAME, CONF_PASSWORD, CONF_SCAN_INTERVAL, CONF_MTU
from .tplink_monitor import fetch_port_statistics, fetch_system_info

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities):
    """Set up TP-Link sensors from a config entry."""
    config = hass.data[DOMAIN][entry.entry_id]

    ip = config[CONF_IP]
    username = config[CONF_USERNAME]
    password = config[CONF_PASSWORD]
    scan_interval = config.get(CONF_SCAN_INTERVAL, 60)  # Default to 60s
    mtu = config.get(CONF_MTU, 1500)  # Default MTU

    coordinator = TPLinkCoordinator(hass, ip, username, password, scan_interval, mtu)

    _LOGGER.debug("Fetching system info for device registration...")
    system_info = await hass.async_add_executor_job(fetch_system_info, ip, username, password)

    if not system_info or "mac_address" not in system_info:
        _LOGGER.error("⚠️ Failed to retrieve system info. Device will NOT be registered.")
        return

    _LOGGER.info(f"✅ System Info Retrieved: {system_info}")

    # Register the device in Home Assistant's device registry
    device_registry = dr.async_get(hass)
    device_entry = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, system_info["mac_address"])},
        manufacturer="TP-Link",
        name=f"TP-Link Switch ({system_info['device_model']})",
        model=system_info["device_model"],
        sw_version=system_info["firmware_version"],
        hw_version=system_info["hardware_version"],
        configuration_url=f"http://{system_info['ip_address']}",
    )

    _LOGGER.info(f"✅ Device registered: {device_entry.name}")

    # Wait for first coordinator update to get port data
    await coordinator.async_config_entry_first_refresh()

    # Dynamically detect available ports from the actual data
    available_ports = []
    if coordinator.data:
        available_ports = list(coordinator.data.keys())
        _LOGGER.info(f"🔍 Detected {len(available_ports)} ports: {sorted(available_ports)}")
    else:
        _LOGGER.warning("⚠️ No port data available, falling back to default 16 ports")
        available_ports = list(range(1, 17))  # Fallback to 16 ports

    # Create sensors only for detected/available ports
    sensors = [TplinkPortSensor(coordinator, port, system_info["mac_address"]) for port in available_ports]
    async_add_entities(sensors, True)

    _LOGGER.info(f"✅ Created {len(sensors)} port sensors for available ports")


class TPLinkCoordinator(DataUpdateCoordinator):
    """Fetch TP-Link switch data at a configured interval asynchronously."""

    def __init__(self, hass, ip, username, password, scan_interval, mtu):
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="TP-Link Bandwidth Monitor",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.hass = hass
        self.ip = ip
        self.username = username
        self.password = password
        self.mtu = mtu
        self.system_info = None
        self.detected_ports = set()  # Track detected ports

    async def _async_update_data(self):
        """Fetch latest switch statistics asynchronously using `requests`."""
        try:
            port_stats = await self.hass.async_add_executor_job(
                fetch_port_statistics, self.ip, self.username, self.password
            )
            
            # Track newly detected ports for logging
            if port_stats:
                new_ports = set(port_stats.keys()) - self.detected_ports
                if new_ports:
                    _LOGGER.info(f"🔍 New ports detected: {sorted(new_ports)}")
                    self.detected_ports.update(new_ports)
                    
        except Exception as e:
            _LOGGER.error(f"Error fetching port statistics: {e}")
            return None

        # Fetch system info only once
        if not self.system_info:
            try:
                _LOGGER.debug("Attempting to fetch system info...")
                self.system_info = await self.hass.async_add_executor_job(
                    fetch_system_info, self.ip, self.username, self.password
                )
                if not self.system_info:
                    _LOGGER.error("System info returned empty!")
                else:
                    _LOGGER.info(f"System Info Retrieved: {self.system_info}")
            except Exception as e:
                _LOGGER.error(f"Error fetching system info: {e}")
                self.system_info = None  # Explicitly set to None on failure

        return port_stats


class TplinkPortSensor(CoordinatorEntity, Entity):
    """Representation of a TP-Link Switch Port Sensor."""

    def __init__(self, coordinator, port, device_mac):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._port = port
        self._device_mac = device_mac  # Link this port to the device MAC
        self._attr_name = f"Port {port} Bandwidth"
        self._prev_rx_good = None
        self._prev_tx_good = None
        self._rx_mbps = 0
        self._tx_mbps = 0
        self._attr_unit_of_measurement = "Mbps"
        self._attr_device_class = "data_rate"
        self._attr_state_class = "measurement"

    @property
    def unique_id(self):
        """Return a unique ID for this sensor."""
        return f"{self._device_mac}_port_{self._port}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information for the TP-Link switch."""
        system_info = self.coordinator.system_info

        if not system_info:
            _LOGGER.warning("⚠️ System Info is missing, device will not be registered.")
            return None

        return DeviceInfo(
            identifiers={(DOMAIN, self._device_mac)},  # Use device MAC for linking
            name="TP-Link Smart Switch",
            manufacturer="TP-Link",
            model=system_info["device_model"],
            sw_version=system_info["firmware_version"],
            hw_version=system_info["hardware_version"],
            connections={(("mac", self._device_mac))},
            configuration_url=f"http://{system_info['ip_address']}",
        )

    @property
    def available(self):
        """Return True if the port data is available."""
        return (
            self.coordinator.data is not None 
            and self._port in self.coordinator.data
        )

    @property
    def state(self):
        """Return the calculated bandwidth in Mbps."""
        data = self.coordinator.data
        if not data or self._port not in data:
            return 0

        # Get current packet count
        rx_good = data[self._port]["rx_good"]
        tx_good = data[self._port]["tx_good"]

        # Use the polling interval for time_diff
        time_diff = self.coordinator.update_interval.total_seconds()

        if self._prev_rx_good is None or self._prev_tx_good is None:
            self._prev_rx_good = rx_good
            self._prev_tx_good = tx_good
            return 0  # No bandwidth calculation yet

        # Calculate bandwidth
        mtu = self.coordinator.mtu
        self._rx_mbps = (rx_good - self._prev_rx_good) * mtu * 8 / (time_diff * 1e6)
        self._tx_mbps = (tx_good - self._prev_tx_good) * mtu * 8 / (time_diff * 1e6)

        self._prev_rx_good = rx_good
        self._prev_tx_good = tx_good

        return round(self._rx_mbps + self._tx_mbps, 2)

    @property
    def extra_state_attributes(self):
        """Return additional switch statistics."""
        data = self.coordinator.data
        if not data or self._port not in data:
            return {}

        return {
            "state": data[self._port]["state"],
            "link_status": data[self._port]["link_status"],
            "rx_good": data[self._port]["rx_good"],
            "tx_good": data[self._port]["tx_good"],
            "rx_bad": data[self._port]["rx_bad"],
            "tx_bad": data[self._port]["tx_bad"],
            "rx_mbps": round(self._rx_mbps, 2),
            "tx_mbps": round(self._tx_mbps, 2),
        }