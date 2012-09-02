import gobject

from component import (Change, 
                       Component, 
                       prop)
from preset import (ComponentSetting,
                    presets)

class SequenceInformation(object):
    category = None
    def __init__(self, sequence_index, sequence_id=None):
        self.sequence_index = sequence_index
        self.sequence_id = sequence_id

def get_id_index(ids, entry_id, external_format=None, internal_format=None):
    """Match an external id to a sequence id in the msa, return the sequence index or None"""
    try:
        return ids.index(entry_id)
    except ValueError:
        pass
    for i, id in enumerate(ids):
        if id.startswith(entry_id) or entry_id.startswith(id):
            return i
    def make_extractor(x):
        if x is None:
            return lambda s: s
        if callable(x):
            return x
        def extract(s):
            m = x.search(s)
            if m:
                try:
                    return m.group('id')
                except:
                    return m.group()
        return extract
    entry_id = make_extractor(external_format)(entry_id)
    get_id = make_extractor(internal_format)
    if entry_id is None:
        return
    for i, id in enumerate(ids):
        if get_id(id) == entry_id:
            return i
    return None

class SequenceInformationRegistry(Component):
    __gproperties__ = dict(
        msa = (
            gobject.TYPE_PYOBJECT,
            'msa',
            'the multiple sequence alignment containing the sequences',
            gobject.PARAM_READWRITE))
    
    def __init__(self, msa=None):
        Component.__init__(self)
        self.categories = {}
        self.msa = msa
        
    msaview_classname = 'data.sequence_information'

    msa = prop('msa')

    def do_set_property_msa(self, pspec, msa):
        if msa == self.msa:
            return
        self.update_change_handlers(msa=msa)
        self.propvalues.update(msa=msa)
        self.handle_msa_change(msa, Change())
        
    def handle_msa_change(self, msa, change):
        if change.has_changed('sequences'):
            self.clear()
        
    def has_category(self, name):
        return name in self.categories
    
    def add_category(self, name, entries=None):
        if name in self.categories:
            raise ValueError('category already present')
        self.categories[name] = [None] * len(self.msa.sequences)
        if entries is not None:
            self.add_entries(entries)
        return self.categories[name]

    def setdefault(self, name):
        """Return the category, or create an empty one if it does not exist."""
        category = self.categories.get(name, None)
        if category:
            return category
        return self.add_category(name)
        
    def remove_category(self, name):
        removed_entries = [e for e in self.categories.pop(name) if e is not None]
        if removed_entries:
            self.emit('changed', Change(name, 'removed', removed_entries))
        
    def add_entries(self, entries):
        if isinstance(entries, SequenceInformation):
            entries = [entries]
        new_entries = []
        changed_categories = set([])
        for entry in entries:
            old_entry = self.categories[entry.category][entry.sequence_index]
            if entry != old_entry:
                self.categories[entry.category][entry.sequence_index] = entry
                new_entries.append(entry)
                changed_categories.add(entry.category)
        if new_entries:
            self.emit('changed', Change(changed_categories, 'added', new_entries))
         
    def remove_entries(self, entries):
        if isinstance(entries, SequenceInformation):
            entries = [entries]
        removed_entries = []
        changed_categories = set([])
        for entry in entries:
            if isinstance(entry, SequenceInformation):
                sequence_index = entry.sequence_index
                category = entry.category
            else:
                category, sequence_index = entry
            old_entry = self.categories[category][sequence_index]
            if old_entry is not None:
                self.categories[category][sequence_index] = None
                removed_entries.append(old_entry)
                changed_categories.add(category)
        if removed_entries:
            self.emit('changed', Change(changed_categories, 'removed', removed_entries))
        
    def get_entry(self, category, sequence_index):
        c = self.categories.get(category, None)
        if c:
            return c[sequence_index]
    
    def clear(self):
        self.categories = {}
        self.emit('changed', Change())
        
    def integrate(self, ancestor, name=None):
        msa = ancestor.find_descendant('data.msa')
        if msa is None:
            msa = ancestor.integrate_descendant('data.msa')
            if msa is None:
                raise TypeError('no suitable parent')
        self.msaview_name = msa.add(self, name)
        self.msa = msa
        return self.msaview_name

class SequenceInformationRegistrySetting(ComponentSetting):
    component_class = SequenceInformationRegistry

presets.register_component_defaults(SequenceInformationRegistrySetting)
        
