import re

import gobject

import action
from computation import (ComputeManager,
                         global_compute_manager)
from preset import (ComponentSetting,
                    Setting,
                    SettingComponentList,
                    SettingList,
                    presets)

ALL_ASPECTS_CHANGED = 'all_aspects_changed'

class Change(object):
    def __init__(self, aspects=None, type=None, data=None):
        if aspects is None:
            aspects = set([ALL_ASPECTS_CHANGED])
        elif isinstance(aspects, str):
            aspects = set([aspects])
        else:
            aspects = set(aspects)
        self.aspects = aspects
        self.type = type
        self.data = data
        
    def has_changed(self, aspects):
        if isinstance(aspects, str):
            aspects = [aspects]
        return ALL_ASPECTS_CHANGED in self.aspects or self.aspects.intersection(aspects)

class Connection(object):
    def __init__(self, source, id):
        self.source = source
        self.id = id
        
    @classmethod
    def change_handler(cls, source, handler, name=None, args=None):
        if isinstance(handler, Component):
            handler = getattr(handler, 'handle_%s_change' % name)
        if args is None:
            args = []
        id = source.connect('changed', handler, *args)
        return cls(source, id)

    def disconnect(self):
        self.source.disconnect(self.id)

def prop(name, readonly=False):
    def get(self):
        return getattr(self.props, name)
    if readonly:
        return property(get)
    def set(self, value):
        setattr(self.props, name, value)
    return property(get, set)

def _make_msaview_name(component):
    name = component._msaview_name 
    if name is None:
        r = re.compile(r'[A-Z]+(?=[A-Z]|$)|[A-Z][^A-Z]*')
        it = r.finditer(component.__class__.__name__)
        name = '_'.join(m.group(0).lower() for m in it)
    return name

class Component(gobject.GObject):
    __gsignals__ = dict(
        changed = (
            gobject.SIGNAL_RUN_FIRST, 
            gobject.TYPE_NONE, 
            (gobject.TYPE_PYOBJECT,)),
        descendant_added = (
            gobject.SIGNAL_RUN_LAST, 
            gobject.TYPE_PYOBJECT, 
            (gobject.TYPE_PYOBJECT, gobject.TYPE_PYOBJECT)),
        descendant_removed = (
            gobject.SIGNAL_RUN_FIRST, 
            gobject.TYPE_NONE, 
            (gobject.TYPE_PYOBJECT,)),
        )

    msaview_classname = None
    msaview_name = None

    propdefaults = {}    
    
    def __init__(self):
        gobject.GObject.__init__(self)
        self.parent = None
        self.children = []
        self.connections = {}
        self.propvalues = {}
        self.fromsettings = None
        self.reset()
    
    def do_get_property(self, pspec):
        name = pspec.name.replace('-', '_')
        explicit_getter = getattr(self, 'do_get_property_' + name, None)
        if explicit_getter:
            return explicit_getter(pspec)
        if name in self.propvalues:
            return self.propvalues[name]
        return getattr(pspec, 'default_value', self.propdefaults.get(name, None))

    def do_set_property(self, pspec, value):
        name = pspec.name.replace('-', '_')
        explicit_setter = getattr(self, 'do_set_property_' + name, None)
        if explicit_setter:
            explicit_setter(pspec, value)
            return
        self.propvalues[name] = value
    
    def update_change_handlers(self, **kw):
        for name, source in kw.items():
            try:
                self.connections.pop(name).disconnect()
            except KeyError:
                pass
            if source is not None:
                self.connections[name] = Connection.change_handler(source, self, name)
      
    def handle_descendant_added(self, component, descendant, name):
        return self.emit('descendant_added', descendant, name)

    def handle_descendant_removed(self, component, descendant):
        if descendant in self.children:
            i = self.children.index(descendant)
            self.children.pop(i)
            for handler_id in self.connections['children'].pop(i):
                descendant.disconnect(handler_id)
        self.emit('descendant_removed', descendant)
 
    def add(self, child, name=None):
        child.set_parent(self)
        self.children.append(child)
        add_signal = child.connect('descendant_added', self.handle_descendant_added)
        remove_signal = child.connect('descendant_removed', self.handle_descendant_removed)
        self.connections.setdefault('children', []).append((add_signal, remove_signal))
        name = self.emit('descendant_added', child, name)
        return name
        
    def set_parent(self, parent):
        """Called by parent.add(). There is normally no other need to call this method."""
        if self.parent is not None:
            raise ValueError('parent already set')
        self.parent = parent
        
    def remove(self, child):
        if not child in self.children:
            raise ValueError('not a direct child')
        child.unparent()
        
    def unparent(self):
        while self.children:
            # The actual removal is done by the descendant_removed signal handler.
            self.children[0].unparent()
        self.parent = None
        self.emit('descendant_removed', self)
        
    def integrate(self, ancestor, name=None):
        self.msaview_name = ancestor.add(self, name)
        return self.msaview_name 

    def integrate_descendant(self, descendant, name=None):
        if isinstance(descendant, basestring):
            descendant = presets.get_setting(descendant)
        setting = descendant
        descendant = setting.component_class()
        descendant.integrate(self, name)
        descendant.from_settings(setting)
        return descendant

    def find_ancestor(self, test):
        if isinstance(test, str):
            msaview_classname = test
            def test(c):
                return c.msaview_classname == msaview_classname
        if test(self):
            return self
        if self.parent is None:
            return None
        return self.parent.find_ancestor(test)
    
    def find_descendant(self, test):
        if isinstance(test, str):
            msaview_classname = test
            def test(c):
                return c.msaview_classname == msaview_classname
        if test(self):
            return self
        # reverse, because then integrations operate on last integrated
        # suitable parent by default, which is handy.
        for child in reversed(self.children):
            found = child.find_descendant(test)
            if found is not None:
                return found
        return None   
    
    def get_compute_manager(self):
        def has_compute_manager(c):
            return isinstance(getattr(c, 'compute_manager', None), ComputeManager)
        m = self.find_ancestor(has_compute_manager)
        if not m:
            return global_compute_manager
        return m.compute_manager
        
    def get_actions(self, coord=None):
        return action.get_applicable(self, coord)
    
    def run_action(self, test, coord=None, params=None, parse=False):
        action.run_action(self, test, coord, params, parse)
    
    def get_options(self):
        return []
    
    def set_options(self, options):
        for o in options:
            setattr(self, o.propname, o.value)

    def from_settings(self, setting):
        self.reset()
        for n in setting.settings:
            s = setting.get_setting(n)
            if s is None:
                continue
            if isinstance(s, ComponentSetting):
                self.integrate_descendant(s)
            elif (isinstance(s, SettingComponentList) or 
                  (isinstance(s, SettingList) and 
                   issubclass(s.element_setting_type, ComponentSetting))):
                for t in s.get_settings():
                    self.integrate_descendant(t)
            else:
                value = s.get_value()
                if value is None:
                    value = self.propdefaults[n]
                setattr(self, n, value)
        if setting.name:
            setting = presets.get_setting(setting.name)
        self.fromsettings = setting
    
    def reset(self):
        self.propdefaults = dict(self.__class__.propdefaults)
        self.fromsettings = None
        for k, v in self.propdefaults.items():
            if isinstance(v, (dict, list)):
                v = v.__class__(v)
            if isinstance(v, Setting):
                v = v.get_value()
            self.propdefaults[k] = v
            self.propvalues[k] = v
        
# XXX all below from old core.__init__

class ComponentRegister(object):
    def __init__(self, components=None, names=None, counters=None):
        if components is None:
            components = []
        if counters is None:
            counters = {}
        self.components = components
        self.counters = {}
        
    def _make_name(self, component):
        base = component.msaview_classname 
        i = self.counters.setdefault(base, 1)
        self.counters[base] += 1
        return base + str(i)
            
    def register(self, component, name=None):
        if self.has_name(name):
            raise KeyError('component already registered')
        if name is None:
            name = self._make_name(component)
        elif self.has_name(name):
            raise KeyError('name already registered')
        self.components.append([component, name])
        return name
    
    def index(self, component=None, name=None):
        query = name or component
        index = 1 if name else 0
        try:
            return (i for i, t in enumerate(self.components) if t[index] == query).next()
        except StopIteration:
            raise ValueError('no match for %r' % query) 
        
    def unregister(self, component):
        self.components.pop(self.index(component))
        
    def rename(self, component, name):
        if self.has_name(name):
            raise KeyError('name already registered')
        self.components[self.index(component)][1] = name

    def has_component(self, component):
        return component in (c for c, n in self.components)
    
    def has_name(self, name):
        return name in (n for c, n in self.components)

    def component(self, name):
        return self.components[self.index(name=name)][0]
            
    def name(self, component):
        return self.components[self.index(component)][1]
            
    def get_component(self, name):
        try:
            return self.component(name)
        except ValueError:
            return None
            
    def get_name(self, component):
        try:
            return self.name(component)
        except ValueError:
            return None

class Root(Component):
    msaview_classname = 'root'
    def __init__(self):
        Component.__init__(self)
        self.descendants = ComponentRegister()
        self.compute_manager = ComputeManager()
        
    def handle_descendant_added(self, component, descendant, name):
        temp = self.emit('descendant-added', descendant, name)
        if temp is not None:
            name = temp
        name = self.descendants.register(descendant, name)
        return name

    def handle_descendant_removed(self, component, descendant):
        self.descendants.unregister(descendant)
        Component.handle_descendant_removed(self, component, descendant)
         
    def add(self, child, name=None):
        name = self.descendants.register(child, name)
        Component.add(self, child, name)
        return name
        
    def unparent(self):
        Component.unparent(self)
        self.descendants = ComponentRegister()
        
    def add_action(self, target, name, action):
        if not isinstance(target, str):
            target = target.msaview_name
        self.actions.setdefault(target, {})[name] = action

def get_name_tree(component, root=None):
    if root is None:
        root = component.find_ancestor('root')
    if component.msaview_classname == 'root':
        name = 'root'
    else:
        name = root.descendants.name(component)
    if component.children:
        return [name, [get_name_tree(c, root) for c in component.children]]
    return name

