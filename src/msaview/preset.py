import os
import re

import xml.etree.ElementTree as etree

import pango

class NamespaceIgnorantTreeBuilder(etree.TreeBuilder):
    xmlns = None
    
    @classmethod
    def strip_xmlns(self, tag):
        if tag.startswith('{'):
            return tag.split('}', 1)[1]
        return tag
        
    def start(self, tag, attrs):
        tag = self.strip_xmlns(tag)
        etree.TreeBuilder.start(self, tag, attrs)
        
    def end(self, tag):
        tag = self.strip_xmlns(tag)
        etree.TreeBuilder.end(self, tag)

class NamespaceIgnorantXMLTreeBuilder(etree.XMLTreeBuilder):
    def __init__(self, html=0, target=None):
        if target is None:
            target = NamespaceIgnorantTreeBuilder()
        etree.XMLTreeBuilder.__init__(self, html, target)

def indent(elem, level=0):
    i = "\n" + level*"  "
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "  "
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
        for elem in elem:
            indent(elem, level+1)
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i
            
def to_preset_file_xml(root_name, presets, comment=None):
    root = etree.Element(root_name)
    if comment:
        root.append(etree.Comment(comment))
    for p in presets:
        root.append(p)
    indent(root)
    return etree.tostring(root)
    
class Presets(object):
    def __init__(self):
        self.presets = {}
        self.setting_types = {}
        self.preset_path = []
        self.preset_files = []
        self.builtins = {}
        
    def register_type(self, type_name, type):
        self.setting_types[type_name] = type
        
    def register_component_defaults(self, type):
        component = type.component_class()
        type_name = component.msaview_classname
        self.register_type(type_name, type)
        self.add_builtin(type_name + ':builtin', component)
        
    def add_builtin(self, name, value):
        setting_type = self.setting_types[name.split(':')[0]]
        settings = setting_type.from_value(value)
        self.add_preset(name, settings)
        self.builtins[name] = settings

    def add_preset(self, name, preset, builtin=False):
        preset.name = name
        preset.presets = self
        self.presets[name] = preset
        if builtin:
            self.builtins[name] = preset
        
    def get_preset(self, name):
        if ':' in name:
            return self.presets[name]
        return self.presets[name + ':builtin']
    
    def get_setting(self, frompreset):
        type = frompreset.split(':')[0]
        if ':' not in frompreset:
            frompreset = frompreset + ':builtin'
        return self.setting_types[type](frompreset=frompreset)
    
    def get_element(self, name):
        preset = self.get_preset(name)
        element = etree.Element('preset', name=name)
        preset.encode(element)
        return element
    
    def get_xml(self, name):
        e = self.get_element(name)
        indent(e)
        return etree.tostring(e)

    def get_value(self, name):
        return self.get_preset(name).get_value()

    def add_to_preset_path(self, path):
        """Add a directory (or a file's containing directory) to the preset search path."""
        if os.path.isfile(path):
            path = os.path.dirname(path)
        self.preset_path.append(path)

    @classmethod
    def read_preset_file(self, f):
        tree = etree.parse(f)
        return [e for e in tree.findall("./preset")]
    
    def import_preset_file(self, f, refresh=False):
        for e in self.read_preset_file(f):
            try:
                type, name = e.attrib['name'].split(':')
                setting_type = self.setting_types[type]
            except KeyError, ValueError:
                continue
            setting = setting_type.from_element(e)
            setting.presetfile = f.name
            self.add_preset(e.attrib['name'], setting)
        if not refresh:
            self.preset_files.append(f.name)
    
    def import_presets(self, path=None, extension='.mxml'):
        if path is None:
            path = self.preset_path
        for dir in path:
            if not os.path.isdir(dir):
                continue
            for preset_file in os.walk(dir).next()[2]:
                if not preset_file.endswith(extension):
                    continue
                f = open(os.path.join(dir, preset_file))
                self.import_preset_file(f)
                f.close()

    def refresh_presets(self):
        for preset in self.builtins.values():
            preset.presetfile = None
        self.presets = dict(self.builtins)
        for preset_file in self.preset_files:
            f = open(preset_file)
            self.import_preset_file(f, refresh=True)
            f.close()
            
presets = Presets()

class Setting(object):
    """Extend all methods to read, store, write and return values."""
    def __init__(self, frompreset=None, preset_registry=None):
        if preset_registry is None:
            preset_registry = presets
        self.frompreset = frompreset
        self.presets = preset_registry
        self.presetfile = None
        self.name = None
    
    @classmethod
    def from_element(cls, element):
        setting = cls()
        setting.parse(element)
        return setting
    
    @classmethod
    def from_child(cls, parent, pattern):
        child = parent.find(pattern)
        if child is None:
            return
        return cls.from_element(child)
    
    def parse(self, element):
        self.frompreset = element.attrib.get('frompreset', None)
        
    def encode(self, element):
        if self.frompreset:
            element.attrib['frompreset'] = self.frompreset

    def to_child(self, parent, tag):
        self.encode(etree.SubElement(parent, tag))
            
    def get_value(self):
        if self.frompreset:
            return self.presets.get_value(self.frompreset)

class SimpleSetting(Setting):
    def __init__(self, value=None, frompreset=None, preset_registry=None):
        Setting.__init__(self, frompreset, preset_registry)
        self.value = value

    def parse(self, element, attrib_name='value'):
        Setting.parse(self, element)
        self.value = element.attrib.get(attrib_name, None)
        
    def encode(self, element, attrib_name='value'):
        Setting.encode(self, element)
        if self.value is not None:
            element.attrib[attrib_name] = str(self.value)

    def get_value(self):
        return self.value or Setting.get_value(self)
    
    @classmethod
    def from_value(cls, value, frompreset=None, preset_registry=None):
        return cls(value, frompreset, preset_registry)

class IntSetting(SimpleSetting):
    def parse(self, element):
        SimpleSetting.parse(self, element)
        if self.value is not None:
            self.value = int(self.value) 
        
class FloatSetting(SimpleSetting):
    def parse(self, element):
        SimpleSetting.parse(self, element)
        if self.value is not None:
            self.value = float(self.value) 
        
    def encode(self, element):
        Setting.encode(self, element)
        if self.value is not None:
            element.attrib['value'] = repr(self.value)

class RegexSetting(SimpleSetting):
    flags = re.IGNORECASE
    def parse(self, element):
        SimpleSetting.parse(self, element)
        if self.value is not None:
            self.value = re.compile(self.value, self.flags) 
        
    def encode(self, element):
        Setting.encode(self, element)
        if self.value is not None:
            element.attrib['value'] = repr(self.value.pattern)

class FontSetting(SimpleSetting):
    def parse(self, element):
        SimpleSetting.parse(self, element)
        if self.value is not None:
            self.value = pango.FontDescription(self.value) 
        
class TextSetting(SimpleSetting):
    def parse(self, element):
        Setting.parse(self, element)
        if element.text:
            self.value = element.text
        
    def encode(self, element):
        Setting.encode(self, element)
        if self.value is not None:
            element.text = self.value

presets.register_type('string', SimpleSetting)
presets.register_type('font', FontSetting)
# May be overridden by later preset definitions (for example in in preset files).
presets.add_builtin('font:default', pango.FontDescription())

class BoolSetting(SimpleSetting):
    def parse(self, element):
        SimpleSetting.parse(self, element)
        if self.value is not None:
            if self.value.lower() in ('true', 'yes', '1', 'on'):
                self.value = True
            elif self.value.lower() in ('false', 'no', '0', 'off'):
                self.value = False
            else:
                raise ValueError('unrecognized boolean literal %r' % self.value)

class SettingList(Setting):
    tag = ''
    element_setting_type = Setting
    def __init__(self, settings=None, frompreset=None, preset_registry=None):
        Setting.__init__(self, frompreset, preset_registry)
        if settings is None:
            settings = []
        self.settings = settings
        
    @classmethod
    def from_value(cls, value, frompreset=None, preset_registry=None):
        settings = [cls.element_setting_type.from_value(v, preset_registry=preset_registry) for v in value]
        return cls(settings, frompreset, preset_registry)
    
    def parse(self, element):
        Setting.parse(self, element)
        self.settings = [self.element_setting_type.from_element(e) for e in element.findall('./' + self.tag)]
    
    def encode(self, element):
        Setting.encode(self, element)
        for setting in self.settings:
            setting.encode(etree.SubElement(element, self.tag))

    def get_specified(self):
        specified = []
        for setting in self.settings:
            specified.append(setting.get_value())
        return specified

    def get_value(self):
        value = Setting.get_value(self) or []
        value.extend(self.get_specified())
        return value

    def get_settings(self):
        settings = []
        if self.frompreset:
            settings.extend(self.presets.get_preset(self.frompreset).get_settings())
        settings.extend(self.settings)
        return settings
    
class SettingStruct(Setting):
    setting_types = {}

    def __init__(self, settings=None, frompreset=None, preset_registry=None):
        for v in settings.values() if settings else []:
            if v.__class__.__name__ == 'Gradient':
                raise ValueError
        Setting.__init__(self, frompreset, preset_registry)
        if settings is None:
            settings = dict.fromkeys(self.setting_types)
        self.settings = settings
        
    def __getitem__(self, key):
        setting = self.settings[key]
        if setting is None and self.frompreset:
            return self.presets.get_preset(self.frompreset)
        return setting
        
    def __setitem__(self, key, value):
        self.settings[key] = value
        
    @classmethod
    def from_value(cls, value, fromvalue=None, preset_registry=None):
        settings = dict.fromkeys(cls.setting_types)
        for name, v in value.items():
            settings[name] = cls.setting_types[name].from_value(v, preset_registry=preset_registry)
        return cls(settings, fromvalue, preset_registry) 

    def parse(self, element):
        Setting.parse(self, element)
        self.settings = {}
        for name, element_setting_type in self.setting_types.items():
            self.settings[name] = element_setting_type.from_child(element, './' + name)
        
    def encode(self, element):
        Setting.encode(self, element)
        for name, setting in self.settings.items():
            if setting:
                setting.to_child(element, name)

    def get_specified(self):
        d = {}
        for n, setting in self.settings.items():
            if not setting:
                continue
            d[n] = setting.get_value()
        return d
        
    def get_value(self):
        value = dict.fromkeys(self.setting_types)
        if self.frompreset:
            value.update(self.presets.get_value(self.frompreset))
        value.update(self.get_specified())
        return value

    def get_setting(self, name):
        setting = self.settings.get(name, None)
        if self.frompreset:
            if setting is None:
                return self.presets.get_preset(self.frompreset).get_setting(name)
            if isinstance(setting, (SettingComponentList, SettingList)):
                s = setting.__class__()
                s.settings = self.presets.get_preset(self.frompreset).get_setting(name).settings + setting.settings
                return s
        return setting

class ComponentSetting(SettingStruct):
    component_class=None
    @classmethod
    def from_value(cls, component, preset_registry=None):
        frompreset = None
        old_values = {}
        if component.fromsettings:
            frompreset = component.fromsettings.name or component.fromsettings.frompreset
            if ':' in frompreset:
                old_values = component.fromsettings.get_value()
            else:
                old_values = presets.get_value(frompreset)
            old_values.update((n, component.propdefaults[n]) for n, v in old_values.items() if v is None)
        else:
            old_values = component.propdefaults
        settings = dict((n, t.from_value(getattr(component, n))) for n, t in cls.setting_types.items())
        setting = cls(settings, frompreset, preset_registry)
        new_values = setting.get_value()
        for name, old_value in old_values.items():
            if (new_values[name] is None or 
                new_values[name] == old_value or
                (issubclass(cls.setting_types[name], SettingComponentList) and not (new_values[name] or old_value))):
                setting.settings[name] = None
        return setting

    def encode(self, element):
        Setting.encode(self, element)
        for name, setting in self.settings.items():
            if self.frompreset and issubclass(self.setting_types[name], SettingComponentList):
                old_values = self.presets.get_value(self.frompreset)[name]
                new_values = self.get_value()[name]
                if new_values == old_values:
                    continue
            if setting:
                setting.to_child(element, name)

    def get_setting(self, name):
        setting = self.settings.get(name, None)
        if self.frompreset:
            if setting is None:
                return self.presets.get_preset(self.frompreset).get_setting(name)
            if isinstance(setting, (SettingComponentList, SettingList)):
                s = setting.__class__()
                s.settings = list(setting.settings)
                s.frompreset = setting.frompreset
                return s
        return setting
    
class SettingComponentList(Setting):
    tag = ''
    def __init__(self, settings=None, frompreset=None, preset_registry=None):
        Setting.__init__(self, frompreset, preset_registry)
        if settings is None:
            settings = []
        self.settings = settings
        
    def __getitem__(self, index):
        return self.settings.__getitem__(index)
        
    def __setitem__(self, index, value):
        return self.settings.__setitem__(index, value)
        
    @classmethod
    def from_value(cls, value, frompreset=None, preset_registry=None):
        if preset_registry is None:
            preset_registry = presets
        settings = [preset_registry.setting_types[v.msaview_classname].from_value(v, preset_registry=preset_registry) for v in value]
        return cls(settings, frompreset, preset_registry)
    
    def parse(self, element):
        self.settings = []
        for e in element.findall('./' + self.tag):
            setting_type = e.attrib['frompreset'].split(':')[0]
            self.settings.append(self.presets.setting_types[setting_type].from_element(e))
    
    def encode(self, element):
        Setting.encode(self, element)
        for setting in self.settings:
            setting.encode(etree.SubElement(element, self.tag))

    def get_specified(self):
        return [(setting.component_class, setting.get_value()) for setting in self.settings]

    def get_value(self):
        return self.get_specified() or Setting.get_value(self) or [] 
    
    def get_settings(self):
        return self.settings or self.presets.get_preset(self.frompreset).get_settings() or []
    
    def to_child(self, parent, tag):
        if not self.settings:
            return 
        Setting.to_child(self, parent, tag)

USER_PRESET_DIR = os.path.expanduser(os.path.join('~', '.msaview', 'presets'))
USER_PRESET_FILE = os.path.join(USER_PRESET_DIR, 'user_presets.mxml')

def read_user_preset_file():
    if not os.path.isfile(USER_PRESET_FILE):
        return []
    f = open(USER_PRESET_FILE)
    elements = Presets.read_preset_file(f)
    f.close()
    return elements

def write_user_preset_file(elements):
    if not os.path.isdir(USER_PRESET_DIR):
        os.makedirs(USER_PRESET_DIR)
    f = open(USER_PRESET_FILE, 'w')
    comment = "Msaview user preset file. This file is automatically generated. Do not edit."
    print >> f, to_preset_file_xml('msaview', elements, comment)
    f.close()

def save_to_preset_file(path, preset_name, preset_registry=None):
    if preset_registry is None:
        preset_registry = presets
    preset_element = preset_registry.get_element(preset_name)
    elements = []
    if os.path.isfile(path):
        f = open(path)
        elements = preset_registry.read_preset_file(f)
        f.close()
    for i, e in enumerate(elements):
        if e.attrib['name'] == preset_name:
            elements[i] = preset_element
            break
    else:
        elements.append(preset_element)
    f = open(path, 'w')
    comment = "Msaview exported presets."
    print >> f, to_preset_file_xml('msaview', elements, comment)
    f.close()

def save_to_user_preset_file(preset_name, preset_registry=None):
    if preset_registry is None:
        preset_registry = presets
    preset_element = preset_registry.get_element(preset_name)
    elements = read_user_preset_file()
    for i, e in enumerate(elements):
        if e.attrib['name'] == preset_name:
            elements[i] = preset_element
            break
    else:
        elements.append(preset_element)
    write_user_preset_file(elements)
    preset = preset_registry.get_preset(preset_name)
    preset.presetfile = USER_PRESET_FILE

def remove_from_user_preset_file(preset_name, preset_registry=None):
    elements = read_user_preset_file()
    i = 0
    while True:
        if i == len(elements):
            raise ValueError('no such user preset')
        if elements[i].attrib['name'] == preset_name:
            elements.pop(i)
            break
        i += 1
    write_user_preset_file(elements)
    
def validate_presets(root, filter=None, verbose=False, preset_registry=None):
    preset_registry = preset_registry or presets
    from pprint import pprint
    def debug_print(*args):
        if verbose:
            print ' '.join(args)
    debug_print("i am msaview test, validating presets")
    for name, preset in preset_registry.presets.items():
        if filter and not name.startswith(filter):
            continue
        try:
            debug_print("###", name)
            debug_print(preset_registry.get_xml(name))
            value = preset_registry.get_value(name)
            debug_print(value)
            if name.startswith('color:'):
                debug_print(value.to_str()[1:])
            elif name.startswith('colormap.regex:'):
                for regex, color in value.items():
                    debug_print(" +", color.to_str(), repr(regex.pattern))
            elif name.startswith('colormap:'):
                for residues, color in value.items():
                    debug_print(" +", color.to_str(), residues)
            elif name.startswith('gradient:'):
                for position, color in value.colorstops:
                    debug_print(" -", position, color.to_str())
            elif isinstance(preset, ComponentSetting):
                c = root.integrate_descendant(preset)
                for n, v in value.items():
                    debug_print(" * %s: %s" % (n, getattr(c, n)))
                root.unparent()
                if root.descendants.components:
                    raise ValueError('improper unparenting by %s preset' % name)
            debug_print()
        except:
            print "Error caused by preset in file", name, preset.presetfile or '<builtin>' 
            raise
    