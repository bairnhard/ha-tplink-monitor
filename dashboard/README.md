## Dashboard

The TP-LINK integration can be used with [Flex Table Card](https://github.com/custom-cards/flex-table-card)
to create a 8/16/24-port monitoring table for the TP-LINK Router

YAML is provided for a sample dashboard that can be modified as needed.  The HACS 'card-mod 4' resource
https://github.com/thomasloven/lovelace-card-mod is also used to add CSS needed to dynamically resize the 
card to the width of the table.

### Install Flex Table Card and Card Mod

Install `flex-table-card` through HACS:

1. Open HACS.
2. Select **Frontend**.
3. Search for **flex-table-card**.
4. Install it.

5. Search for **card-mod**.
6. Install it.
7. Restart Home Assistant if requested.

### Dashboard card

After installing the TP-Link integration, Flex Table Card and optionally card-mod, add a **Manual** card to your
dashboard and paste the contents of:

`dashboard/tplink_dashboard_table.yaml`

The card displays:

- Port number
- Port name
- Link status
- Rx total
- Tx total
- Current bandwidth

Bandwidth is displayed in Kbps and color coded according to traffic level.
Rx and Tx totals are display in total bytes and turn red if TPlink reports rx_bad or tx_bad on any link.

Note that if card-mod is not used the table may overflow the card width.
