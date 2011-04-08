import os
import subprocess
import tempfile

from msaview.action import (Action,
                            register_action)
from msaview.options import Option
from msaview.preset import (Setting,
                            TextSetting,
                            presets)

presets.add_to_preset_path(__file__)

def get_pymol_path():
    for dir in os.environ["PATH"].split(os.pathsep):
        path = os.path.join(dir, 'pymol')
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path

PYMOL_PATH = get_pymol_path()
PYMOL_AVAILABLE = PYMOL_PATH is not None

def fix_indent(text):
    lines = []
    for line in text.splitlines():
        if not lines and not line.strip():
            continue
        if not lines:
            indent = len(line) - len(line.lstrip())
        lines.append(line[indent:])
    while lines and not lines[-1].strip():
        lines.pop(-1)
    return '\n'.join(lines) + '\n' 

class PymolScriptSetting(TextSetting):
    def parse(self, element):
        TextSetting.parse(self, element)
        if self.value is None:
            return
        self.value = fix_indent(self.value)
        
    def encode(self, element):
        Setting.encode(self, element)
        if self.value is not None:
            element.text = '\n%s' % self.value
    
presets.register_type('pymolscript', PymolScriptSetting)

class ShowStructureInPymol(Action):
    action_name = 'show-structure-in-pymol'
    path = ['External viewer', 'Pymol', 'Show structure for %s']
    tooltip = 'Show structure in the Pymol molecular viewer.'
    
    fetch_cmd = fix_indent("""
        get fetch_path
        python
        cmd._pymol.invocation.options.keep_thread_alive = True
        if cmd.get('fetch_path') == '.':
            cmd.set('fetch_path', %r)
        python end
        fetch %%s, async=0
        """) % tempfile.gettempdir()
        
    @classmethod
    def applicable(cls, target, coord=None):
        if not PYMOL_AVAILABLE:
            return
        if not coord or coord.sequence is None:
            return
        if target.msaview_classname != 'data.msa':
            return
        entry = target.sequence_information.get_entry('pdb-ids', coord.sequence)
        if not (entry and entry.structures):
            return
        actions = []
        for structure in sorted(entry.structures, key=lambda s: s.resolution or 1000000):
            a = cls(target, coord)
            a.params['structure'] = structure
            a.path = list(cls.path)
            label = repr(structure.id)
            details = []
            if structure.resolution is not None:
                details.append(str(structure.resolution) + ' A')
            if structure.method is not None:
                details.append(structure.method)
            if structure.chains is not None:
                details.append(structure.chains)
            if details:
                label += ' (%s)' % ', '.join(details) 
            a.path[-1] %= label
            actions.append(a)
        return actions
    
    def get_options(self):
        return [Option(None, 'pymolscript', 'default', 'default', 'Pymol script', 'How the structure should be visualized in pymol (the preset name of a pymol_script)')]
    
    def set_options(self, options):
        Action.set_options(self, options)
        self.params['pymolscript'] = presets.get_value('pymolscript:' + self.params['pymolscript'])
    
    def run(self):
        structure = self.params['structure']
        startup_script = self.fetch_cmd % structure.id
        startup_script += self.params['pymolscript']
        _buggy_pymol_parser = True
        if _buggy_pymol_parser:
            argv = sum((['-d', s] for s in startup_script.splitlines()), [PYMOL_PATH])
            p = subprocess.Popen(argv, stdin=subprocess.PIPE)
        else:
            p = subprocess.Popen([PYMOL_PATH, '-p'], stdin=subprocess.PIPE)
            p.stdin.write(startup_script)
        p.stdin.close()

register_action(ShowStructureInPymol)
    