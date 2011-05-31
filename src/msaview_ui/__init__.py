#!/usr/bin/env python
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
import os
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
        """Run session, return exit code."""
        try:
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
        except KeyboardInterrupt:
            if self.config:
                print >> sys.stderr, self.config.shorthelp()
            return 1
        except OptionError, e:
            if self.config:
                print self.config.shorthelp()
            print >> sys.stderr, "ERROR: %r is not an acceptable argument for %s (%s)\n" % (e.details[1], e.details[0], e.details[2])
            return 1
        return 0
        
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

def create_session(argv=None):
    """Parse config and return session object or exit code."""
    import tui
    from tui import formats 
    
    class UIAction(tui.formats.Format):
        def __init__(self):
            pass
        
        def __str__(self):
            return "Action"
        
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
        
        def shortname(self):
            return "Action"
        
        def strvalue(self, value):
            def format_action(action_def):
                l = [action_def[0].action_name]
                if action_def[1]:
                    l.append(action_def[1])
                if action_def[2]:
                    l.append(' '.join('='.join(t) for t in action_def[2].items()))
                return ' '.join(l)
            s = str([format_action(v) for v in value[1:]])
            return "%s(%s)" % (self.shortname(), s)
            
        def nargs(self):
            return 1
        
        def docs(self):
            return "An msaview action definition, as ACTION [PATH] [PARAM=VALUE [ ... ]]"
        
    config = tui.tui(progname='MSAView', main=__file__)
    config.makeoption('show-log-settings', formats.Flag, "'no'")
    config.makeoption('import-presets', formats.ReadableFile(acceptemptystring=True), "''", 'i', recurring=True)
    config.makeoption('list-presets', formats.RegEx(acceptemptystring=True), "''", 'l')
    config.makeoption('list-locations', formats.Flag(), "no", 'C')
    config.makeoption('show-presets', formats.RegEx(acceptemptystring=True), "''", 'q')
    config.makeoption('list-actions', formats.Str, "''", 'k')
    config.makeoption('show-actions', formats.Str, "''", 'A')
    config.makeoption('add', formats.Str(), "''", 'a', recurring=True)
    config.makeoption('rename', formats.Format('RenameDef', str, nargs=2), "PATH NAME", 'r', recurring=True)
    config.makeoption('show-tree', formats.Flag(), "no", 'T')
    config.makeoption('show-options', formats.Str(), "''", 'o')
    config.makeoption('modify-option', formats.Format('ModDef', str, nargs=3), "PATH OPTION VALUE", 'm', recurring=True)
    config.makeoption('show-settings', formats.Str, "''", 'D')
    config.makeoption('export-preset', formats.Format('PresetDef', str, nargs=2), "PATH PRESET_NAME", 'x')
    config.makeoption('save-preset', formats.Format('PresetDef', str, nargs=2), "PATH PRESET_NAME")
    config.makeoption('delete-preset', formats.Str(), "''")
    config.makeoption('no-gui', formats.Flag(), "no", 'G')
    config.makeoption('do', UIAction(), None, 'd', recurring=True)
    config.makeposarg('msa_file', formats.ReadableFile, optional=True, recurring=True)
    
    try:
        config.initprog(argv=argv, showusageonnoargs=False)
        options = config.options()
        msa_files = config.posargs()[0]
        if options['show-log-settings']:
            for name in sorted(msaview.log.logger.manager.loggerDict.keys()):
                print name + ':', msaview.log.format_level(name)
            return 0
        if len(msa_files) > 1 and not options['no-gui']:
            raise OptionError('--no-gui', 'yes', 'gui not allowed for multiple MSA_FILEs')
        if options['show-presets']:
            try:
                options['show-presets'] = re.compile(options['show-presets'])
            except:
                raise OptionError('--show-presets', options['show-presets'], 'not a valid regular expression')
        read_presets(options['import-presets'][1:])
        m = msaview.Root()
        build_component_tree(m, options['add'][1:] or ['layout:default'])
        rename_components(m, options['rename'][1:])
        modify_options(m, options['modify-option'][1:])
        if options['show-options']:
            show_options(m, options['show-options'])
            return 0
        if options['show-settings']:
            show_settings(m, options['show-settings'])
            return 0
        if options['list-presets']:
            list_presets(options['list-presets'], options['list-locations'])
            return 0
        if options['show-presets']:
            show_presets(options['show-presets'])
            return 0
        if options['list-actions']:
            list_actions(options['list-actions'])
            return 0
        if options['show-actions']:
            show_actions(options['show-actions'])
            return 0
        if options['show-tree']:
            from pprint import pprint
            pprint(msaview.component.get_name_tree(m))
            return 0
        if options['export-preset'] != ['PATH', 'PRESET_NAME']:
            export_preset(m, *options['export-preset'])
            return 0
        if options['save-preset'] != ['PATH', 'PRESET_NAME']:
            full_preset_name = save_user_preset(m, *options['save-preset'])
            print "\nPreset %r saved to user preset file: %s\n" % (full_preset_name, msaview.USER_PRESET_FILE)
            return 0
        if options['delete-preset']:
            delete_preset(options['delete-preset'])
            print "\nPreset %r removed from user preset file: %s\n" % (options['delete-preset'], msaview.USER_PRESET_FILE)
            return 0
        for a in options['do'][1:]:
            path = a[1]
            if path:
                target = resolve_component_path(m, path, 'do')
                if target is None:
                    raise OptionError('--do', path, 'no such component')
                a[1] = target
    except (OptionError, tui.ParseError), e:
        print config.shorthelp()
        if isinstance(e, OptionError):
            print >> sys.stderr, "ERROR: %r is not an acceptable argument for %s (%s)\n" % (e.details[1], e.details[0], e.details[2])
        else:
            print >> sys.stderr, "ERROR: %s\n" % e
        return 1
    return Session(root=m, 
                   action_defs=options['do'][1:], 
                   msa_files=msa_files, 
                   show_gui=not options['no-gui'],
                   config=config)
    
def main(argv=None):
    session = create_session()
    if isinstance(session, Session):
        return session.run()
    return int(session)

if __name__ == '__main__':
    x = main(sys.argv)
    if x:
        sys.exit(int(x))

