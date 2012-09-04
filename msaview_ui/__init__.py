#!/usr/bin/env python
"""MSAView 
Fast and flexible visualisation of multiple sequence alignments.

Author:    Joel Hedlund <joel@nsc.liu.se>
Contact:   If you have problems with this package, please contact the author.
Copyright: Copyright (c) 2012 Joel Hedlund.
License:   The MIT License.
#Download:  sourceforge whatever

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
import os
import re
import sys
try:
    import xml.etree.cElementTree as etree
except ImportError:
    import xml.etree.ElementTree as etree

import gtk

import msaview

__version__ = msaview.__version__

def show_presets(query):
    presets = [msaview.presets.get_element(name) for name in msaview.presets.presets if query.search(name)]
    if presets:
        print msaview.preset.to_preset_file_xml('msaview', presets)

def list_presets(query, locations=False):
    presets = [t for t in msaview.presets.presets.items() if query.search(t[0])]
    if not presets:
        return
    if locations:
        width = max(len(t[0]) for t in presets)
        format = "%%-%ds  %%s" % width 
        print '\n'.join(format % (n, p.presetfile if p.presetfile else 'builtin') for n, p in sorted(presets))
    else:
        print '\n'.join(t[0] for t in sorted(presets))

def list_actions(query):
    actions = msaview.action.actions
    if query != '-':
        actions = msaview.action.get_actions(query)
    print '\n'.join(a.action_name for a in actions)

def format_action(action):
    out = []
    out.append("ACTION: %s" % action.action_name)
    out.append("  " + action.tooltip)
    for option in action.get_options():
        out.append("  Option: %s" % option.propname)
        out.append("    %s(%s)" % (option.__class__.__name__, option.to_str()))
        out.append("    " + option.tooltip)
    return '\n'.join(out)
    
def show_actions(query):
    actions = msaview.action.actions
    if query != '-':
        actions = msaview.action.get_actions(query)
    print '\n'.join(format_action(a(None)) for a in actions)

def make_gui(m, title=None):
    gui = msaview.gui.GUI(m)
    gui.window.set_title('MSAView GUI - %s' % title)
    return gui

def show_gui(gui, action_defs=None):
    # Some views like to resize themselves based on loaded data (eg. sequence identifiers)
    # This lets all resizing take effect before we attempt to zoom to fit.
    run_actions(gui.root, action_defs or [])
    gtk.main()

def run_action(root, action_class, target, params): 
    if target is None:
        target = msaview.action.find_applicable_target(root, action_class)
        if target is None:
            raise OptionError('--do', '', 'no applicable target for action %s' % action_class.action_name)
    action = action_class.applicable(target)
    options = action.get_options()
    for name, value in params.items():
        option = msaview.action.get_best_matching_name(name, options, lambda o: o.propname)
        if option is None:
            raise OptionError('--do', name, 'action %s has no parameters matching that name' % action.action_name)
        try:
            option.from_str(value)
        except Exception, e:
            raise OptionError('--do', value, 'invalid for parameter %s of action %s: %s' % (name, action.action_name, e))
    action.set_options(options)
    action.run()

def run_actions(root, action_defs):
    for action_def in action_defs:
        while gtk.events_pending():
            gtk.main_iteration(False)
        run_action(root, *action_def)
    while gtk.events_pending():
        gtk.main_iteration(False)

class Session(object):
    def __init__(self, root=None, action_defs=None, msa_files=None, show_gui=False, config=None):
        self.root = root
        self.action_defs = action_defs
        self.msa_files = msa_files
        self.show_gui = show_gui
        self.config = config

    def run(self):
        msa = self.root.find_descendant('data.msa')
        if self.show_gui:
            g = make_gui(self.root)
            if self.msa_files:
                msa.read_fasta(open(self.msa_files[0]))
            show_gui(g, action_defs=self.action_defs)
            return
        if not self.msa_files:
            run_actions(self.root, self.action_defs)
            return
        for msa_file in self.msa_files:
            msa.read_fasta(open(msa_file))
            run_actions(self.root, self.action_defs)
        
# Parameter parsing helpers:

class OptionError(Exception):
    details = None
    def __init__(self, *details):
        Exception.__init__(self)
        self.details = details

def read_presets(preset_files, option_name='--preset-file'):
    for preset_file in preset_files:
        f = open(preset_file)
        try:
            msaview.presets.import_preset_file(f)
        except Exception, e:
            raise OptionError(option_name, f, e)
        f.close()

def resolve_component_path(root, path, option_name):
    component = root.descendants.get_component(path[0]) or root.find_descendant(path[0])
    if not component:
        raise OptionError(option_name, path[0], 'no such component')
    for p in path[1:]:
        c = component.find_descendant(p)
        if not c:
            raise OptionError(option_name, p, 'no such component')
        component = c
    return component

def build_component_tree(root, integrate_defs, option_name='--add'):
    for integrate_def in integrate_defs:
        path = None
        name = None
        if ',' in integrate_def:
            path, integrate_def = integrate_def.split(',', 1)
        if '//' in integrate_def:
            integrate_def, name = integrate_def.split('//', 1)
        preset = integrate_def.strip()
        target = root
        if path is not None:
            target = resolve_component_path(root, path.strip().split('/'), option_name)
        try:
            target.integrate_descendant(preset, name=name.strip() if name else name)
        except Exception, e:
            raise OptionError(option_name, integrate_def, e)

def rename_components(root, rename_defs, option_name='--rename'):
    for path, name in rename_defs:
        c = resolve_component_path(root, path.split('/'), option_name)
        root.descendants.rename(c, name)
    
def show_options(root, path, option_name='--show-options'):
    c = resolve_component_path(root, path.split('/'), option_name)
    options = [o for o in c.get_options() if not isinstance(o, msaview.options.ComponentListOption)]
    if not options:
        print "[no options]"
        return
    for o in options:
        print "%s (%s, %s):" % (o.propname, o.__class__.__name__, o.tooltip)
        print " value: %s" % o.to_str()
        print " default: %s" % o.to_str(o.default)

def modify_options(root, modify_defs, option_name='--modify-option'):
    for path, option, value in modify_defs:
        c = resolve_component_path(root, path.split('/'), option_name)
        try:
            o = (o for o in c.get_options() if o.propname == option).next()
        except Exception, e:
            raise OptionError(option_name, option, 'no such option')
        try:
            o.from_str(value)
        except Exception, e:
            raise OptionError(option_name, value, e)
        c.set_options([o])

def show_settings(root, path, option_name='--show-settings'):
    c = resolve_component_path(root, path.split('/'), option_name)
    s = msaview.presets.setting_types[c.msaview_classname].from_value(c, msaview.presets)
    e = etree.Element('settings')
    s.encode(e)
    msaview.preset.indent(e)
    print etree.tostring(e)

def create_preset(root, path, preset_name, option_name):
    if not preset_name.isalnum():
        raise OptionError(option_name, preset_name, 'must contain alphanumeric characters only')
    c = resolve_component_path(root, path.split('/'), option_name)
    full_preset_name = c.msaview_classname + ':' + preset_name
    msaview.presets.add_builtin(full_preset_name, c)
    preset = msaview.presets.get_preset(full_preset_name)
    preset.presetfile = '<custom>'
    return full_preset_name

def export_preset(root, path, preset_name, option_name='--export-preset'):
    full_preset_name = create_preset(root, path, preset_name, option_name)
    e = msaview.presets.get_element(full_preset_name)
    print msaview.preset.to_preset_file_xml('msaview', [e])

def save_user_preset(root, path, preset_name, option_name='--save-preset'):
    full_preset_name = create_preset(root, path, preset_name, option_name)
    msaview.preset.save_to_user_preset_file(full_preset_name)
    return full_preset_name

def delete_preset(preset_name, option_name='--delete-preset'):
    try:
        msaview.preset.remove_from_user_preset_file(preset_name)
    except Exception, e:
        if str(e) == 'no such user preset':
            raise OptionError(option_name, preset_name, 'no such user preset')
        raise

def main(argv=None):
    """Parse config and return session object or exit code."""
    import tui
    from tui import (Option,
                     ParseError,
                     PositionalArgument as Posarg,
                     get_metainfo,
                     tui)
    from tui.formats import (Flag,
                             Format,
                             ReadableFile,
                             RegEx,
                             String,
                             ) 
    
    class UIAction(Format):
        """An msaview action definition, as ACTION [PATH] [PARAM=VALUE [ ... ]]"""
        name = 'Action'
        def parse(self, args):
            action = msaview.action.get_action(args.pop(0))
            if args[0].startswith('-') or '=' in args[0]:
                target_path = None
            else:
                target_path = args.pop(0).split('/')
            params = {}
            while args:
                if '=' not in args[0]:
                    break
                name, value = args.pop(0).split('=', 1)
                params[name] = value
            return [action, target_path, params]
        
        def parsestr(self, argstr):
            if argstr is None:
                return None
            return self.parse(argstr.split())
        
        def strvaluex(self, value):
            def format_action(action_def):
                l = [action_def[0].action_name]
                if action_def[1]:
                    l.append(action_def[1])
                if action_def[2]:
                    l.append(' '.join('='.join(t) for t in action_def[2].items()))
                return ' '.join(l)
            s = str([format_action(v) for v in value[1:]])
            return "%s(%s)" % (self.shortname(), s)
            
    ui = tui([Option('show-log-settings', Flag),
              Option('import-presets', ReadableFile, 'i', recurring=True),
              Option('list-presets', RegEx, 'l'),
              Option('list-locations', Flag, 'C'),
              Option('show-presets', RegEx, 'q'),
              Option('list-actions', String, 'k'),
              Option('show-actions', String, 'A'),
              Option('add', String, 'a', recurring=True),
              Option('rename', Format(name='RenameDef', nargs=2), 'r', recurring=True),
              Option('show-tree', Flag, 'T'),
              Option('show-options', String, 'o'),
              Option('modify-option', Format(name='ModDef', nargs=3), 'm', recurring=True),
              Option('show-settings', String, 'D'),
              Option('export-preset', Format(name='PresetDef', nargs=2), 'x'),
              Option('save-preset', Format(name='PresetDef', nargs=2)),
              Option('delete-preset', String),
              Option('no-gui', Flag, 'G'),
              Option('do', UIAction(), 'd', recurring=True),
              Posarg('msa-file', ReadableFile, optional=True, recurring=True)],
             __version__,
             msaview,
             argv,
             **get_metainfo(__file__))
    try:
        if ui['show-log-settings']:
            for name in sorted(msaview.log.logger.manager.loggerDict.keys()):
                print name + ':', msaview.log.format_level(name)
            return
        if len(ui['msa-file']) > 1 and not ui['no-gui']:
            ui.graceful_exit()
            raise OptionError('GUI not allowed for multiple MSA_FILEs')
        read_presets(ui['import-presets'])
        m = msaview.Root()
        build_component_tree(m, ui['add'] or ['layout:default'])
        rename_components(m, ui['rename'])
        modify_options(m, ui['modify-option'])
        if ui['show-options']:
            show_options(m, ui['show-options'])
            return
        if ui['show-settings']:
            show_settings(m, ui['show-settings'])
            return
        if ui['list-presets']:
            list_presets(ui['list-presets'], ui['list-locations'])
            return
        if ui['show-presets']:
            show_presets(ui['show-presets'])
            return
        if ui['list-actions']:
            list_actions(ui['list-actions'])
            return
        if ui['show-actions']:
            show_actions(ui['show-actions'])
            return
        if ui['show-tree']:
            from pprint import pprint
            pprint(msaview.component.get_name_tree(m))
            return
        if ui['export-preset']:
            export_preset(m, *ui['export-preset'])
            return
        if ui['save-preset']:
            full_preset_name = save_user_preset(m, *ui['save-preset'])
            print "\nPreset %r saved to user preset file: %s\n" % (full_preset_name, msaview.USER_PRESET_FILE)
            return
        if ui['delete-preset']:
            delete_preset(ui['delete-preset'])
            print "\nPreset %r removed from user preset file: %s\n" % (ui['delete-preset'], msaview.USER_PRESET_FILE)
            return
        for a in ui['do']:
            path = a[1]
            if path:
                target = resolve_component_path(m, path, 'do')
                if target is None:
                    raise OptionError('--do', path, 'no such component')
                a[1] = target
        session = Session(root=m,
                          action_defs=ui['do'], 
                          msa_files=ui['msa-file'], 
                          show_gui=not ui['no-gui'],
                          config=ui)
        session.run()
    except KeyboardInterrupt:
        ui.graceful_exit("Interrupted by user")
    except OptionError, e:
        msg = "ERROR: %r is not an acceptable argument for %s (%s)." 
        ui.graceful_exit(msg % e.details)
    
if __name__ == '__main__':
    sys.exit(main() or 0)

