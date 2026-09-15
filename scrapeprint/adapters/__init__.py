from scrapeprint.adapters.chromium import ChromiumAdapter
from scrapeprint.adapters.obscura import ObscuraAdapter
from scrapeprint.models import Engine

ADAPTERS = {Engine.chromium: ChromiumAdapter, Engine.obscura: ObscuraAdapter}
