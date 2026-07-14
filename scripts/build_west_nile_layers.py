#!/usr/bin/env python3
from sync.west_nile_connector import sync_west_nile_layers
print(sync_west_nile_layers("data/territorial_layers/territorial_layers.csv", "data/territorial_layers/west_nile_surveillance.csv"))
