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
    
ui = tui.tui(progname = 'MSAView', command = 'msaview')
ui.makeoption('loglevel', formats.Str, "''", '-L') 
ui.makeoption('show-log-settings', formats.Flag, "'no'")
ui.makeoption('import-presets', formats.ReadableFile(acceptemptystring=True), "''", 'i', recurring=True)
ui.makeoption('list-presets', formats.Format('RegEx', re.compile, lambda r: repr(r.pattern) if r else "''", acceptemptystring=True), "''", 'l')
ui.makeoption('list-locations', formats.Flag(), "no", 'C')
ui.makeoption('show-presets', formats.Format('RegEx', re.compile, lambda r: repr(r.pattern) if r else "''", acceptemptystring=True), "''", 'q')
ui.makeoption('list-actions', formats.Str, "''", 'k')
ui.makeoption('show-actions', formats.Str, "''", 'A')
ui.makeoption('add', formats.Str(), "''", 'a', recurring=True)
ui.makeoption('rename', formats.Format('RenameDef', str, nargs=2), "PATH NAME", 'r', recurring=True)
ui.makeoption('show-tree', formats.Flag(), "no", 'T')
ui.makeoption('show-options', formats.Str(), "''", 'o')
ui.makeoption('modify-option', formats.Format('ModDef', str, nargs=3), "PATH OPTION VALUE", 'm', recurring=True)
ui.makeoption('show-settings', formats.Str, "''", 'D')
ui.makeoption('export-preset', formats.Format('PresetDef', str, nargs=2), "PATH PRESET_NAME", 'x')
ui.makeoption('save-preset', formats.Format('PresetDef', str, nargs=2), "PATH PRESET_NAME")
ui.makeoption('delete-preset', formats.Str(), "''")
ui.makeoption('no-gui', formats.Flag(), "no", 'G')
ui.makeoption('do', UIAction(), None, 'd', recurring=True)
ui.makeposarg('msa_file', formats.ReadableFile, optional=True, recurring=True)
