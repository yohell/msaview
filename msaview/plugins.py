import os
import sys

class PluginSystem(object):
    def __init__(self, prefix='msaview_plugin_'):
        self.prefix = prefix
    
    def is_plugin(self, path, name):
        if not name.startswith(self.prefix):
            return False
        return (os.path.isfile(os.path.join(path, name + '.py')) or 
                os.path.isfile(os.path.join(path, name, '__init__.py'))) 
    
    def import_plugins(self, globals):
        for dir in sys.path:
            if not os.path.isdir(dir):
                continue
            dirs, files = os.walk(dir).next()[1:3]
            for plugin in dirs + files:
                name = plugin.split('.')[0]
                if name in globals:
                    continue
                if self.is_plugin(dir, name):
                    globals[name] = __import__(name, globals, locals(), [], -1) 

    def import_plugin(self, plugin_path):
        if self.is_plugin(plugin_path):
            raise ValueError('%r is not a plugin' % plugin_path)
        old_path = sys.path
        try:
            sys.path = self.path
            name = plugin[len(self.prefix):]
            self.plugins[name] = __import__(name)
        except:
            raise
        finally:
            sys.path = old_path

def import_plugins():
    plugins = PluginSystem()
    plugins.import_plugins(globals())

import_plugins()

