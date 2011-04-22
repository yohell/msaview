"""MSAView - Fast and flexible visualisation of multiple sequence alignments.

Copyright (c) 2011 Joel Hedlund.

Contact: Joel Hedlund <yohell@ifm.liu.se>

MSAView is a modular, configurable and extensible package for analysing and 
visualising multiple sequence alignments and sequence features. It can import 
and display data from online sources, and it can launch external viewers for 
additional details, such as structures and database pages. MSAView is highly
configurable and has a user extendable preset library, as well as a plugin 
architecture which allows for straightforward extension of the program's 
capabilities.

MSAVIew has a fast graphical user interface that remains responsive even for 
large datasets, as well as a powerful command line client which allows the user
to generate consistent views for hundreds of protein families at a time. All 
the program's functionality is also directly accessible via the python API for
more advanced operations. 
 
If you have problems with this package, please contact the author.

Copyright
=========
 
The MIT License

Copyright (c) 2011 Joel Hedlund.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""

__version__ = "0.9.0"

import os
import sys

# Get logging in place first.
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

