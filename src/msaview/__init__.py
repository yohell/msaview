import os
import sys

import log

import action
import preset
import component

# 3 convenience imports:
from preset import presets
from component import Root
from action import run_action
 
preset.presets.add_to_preset_path(os.path.join(os.path.dirname(__file__), 'data')),
preset.presets.add_to_preset_path('/etc/msaview/presets') 
plugin_path = [os.path.expanduser(os.path.join('~', '.msaview', 'plugins')),
               os.path.join(os.path.dirname(__file__), 'plugins')]
sys.path = sys.path[:1] + plugin_path + sys.path[1:]

import adjustments
import plugins
import color
import gui
import msa
import options
import overlays
import renderers
import sequence_information
import visualization

from preset import (USER_PRESET_DIR, 
                    USER_PRESET_FILE)
preset.presets.add_to_preset_path(USER_PRESET_DIR)
preset.presets.import_presets()

