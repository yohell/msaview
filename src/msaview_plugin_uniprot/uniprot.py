import re
from xml.etree import ElementTree as etree

import gio

from msaview import presets
from msaview.action import (Action,
                               register_action)
from msaview.computation import (DownloadTask,
                                    SimpleETreeDownloader)
from msaview.features import SequenceFeature
from msaview.options import Option
from msaview.selection import Region
from msaview.sequence_information import SequenceInformation

presets.add_to_preset_path(__file__)

class UniprotID(SequenceInformation):
    category = 'uniprot-id'

    @classmethod
    def extract_id(cls, id):
        uniprot_ac = re.compile(r'\b(?P<id>[A-NR-Z][0-9][A-Z][A-Z0-9][A-Z0-9][0-9]|[OPQ][0-9][A-Z0-9][A-Z0-9][A-Z0-9][0-9])(\b|_)')
        sprot_id = re.compile(r'\b(?P<id>[A-Z0-9]{1,5}_[A-Z0-9]{3,5})\b')
        for r in (uniprot_ac, sprot_id):
            m = r.search(id)
            if m:
                return m.group('id')
    
    @classmethod
    def from_msa_sequence(cls, msa, sequence_index):
        id = cls.extract_id(msa.ids[sequence_index])
        return cls(sequence_index, id or None)

class UniprotETree(SequenceInformation):
    category = 'uniprot-etree'
    def __init__(self, sequence_index, sequence_id=None, root=None, offset=None):
        self.sequence_index = sequence_index
        self.sequence_id = sequence_id
        self.root = root
        self.offset = offset

class UniprotXMLDownloadTask(DownloadTask):
    url = "http://www.ebi.ac.uk/cgi-bin/dbfetch?db=uniprotkb&format=uniprotxml&style=raw&id=%s"
    downloader_class = SimpleETreeDownloader
    
    def get_urls(self):
        ids = ','.join(id for i, id in self.id_enumeration[self.progress:self.progress+self.batch_size])
        return [self.url % ids]
    
    def parse_downloads(self, data):
        entries = []
        for sequence_index, sequence_id in self.id_enumeration[self.progress:self.progress+self.batch_size]:
            for entry_element in data[0].getroot().getchildren():
                element_ids = [e.text for e in entry_element.findall('accession')]
                element_ids.append(entry_element.find('name').text)
                if sequence_id not in element_ids:
                    continue
                offset = entry_element.find('sequence').text.find(self.msa.unaligned[sequence_index].upper())
                if offset < 0:
                    continue
                entries.append(UniprotETree(sequence_index, sequence_id, entry_element, offset))
                break
            else:
                entries.append(UniprotETree(sequence_index, sequence_id, None, None))
        return entries

    def update_progress(self, data):
        self.progress = min(self.total, self.progress + self.batch_size) 
        
    def handle_id_category_changed(self, sequence_information, change):
        if change.has_changed('uniprot-id'):
            self.abort()
        
def get_id_entry_for_sequence(msa, sequence_index):
    entry = msa.sequence_information.setdefault('uniprot-id')[sequence_index]
    if entry is None:
        entry = UniprotID.from_msa_sequence(msa, sequence_index)
        msa.sequence_information.add_entries(entry)
    return entry

def get_populated_uniprot_id_category(msa):
    new_entries = []
    for sequence_index, entry in enumerate(msa.sequence_information.setdefault('uniprot-id')):
        if entry is not None:
            continue
        id = UniprotID.from_msa_sequence(msa, sequence_index)
        if id:
            new_entries.append(id)
    msa.sequence_information.add_entries(new_entries)
    return msa.sequence_information.categories['uniprot-id']

def dbfetch_uniprot_xml_for_sequence(msa, sequence_index):
    id_entry = msa.sequence_information.setdefault('uniprot-id')[sequence_index]
    if not id_entry:
        id_entry = UniprotID.from_msa_sequence(msa, sequence_index)
        msa.sequence_information.add_entries(id_entry)
        if not id_entry.sequence_id:
            return
    task = UniprotXMLDownloadTask(msa, [(sequence_index, id_entry.sequence_id)])
    task.run()
    return task.results[0]

class UniprotSequenceFeature(SequenceFeature):
    def __init__(self, sequence_index=None, sequence_id=None, source=None, name=None, region=None, mapping=None, description=None, original_description=None, status=None, id=None, evidence=None, ref=None, original=None, variation=None):
        self.sequence_index = sequence_index
        self.sequence_id = sequence_id
        self.source = source
        self.name = name
        self.region = region
        self.mapping = mapping
        self.description = description
        self.status = status
        self.id = id
        self.evidence = evidence
        self.ref = ref
        self.original = original
        self.variation = variation

    def is_similarly_annotated(self, other):
        if (other.source.lower() != self.source.lower() or
            other.name.lower() != self.name.lower()):
            return False
        try:
            if other.description is self.description is None:
                return True
            return other.description.lower() == self.description.lower()
        except:
            return False
    
    @classmethod
    def from_element(cls, element):
        source = 'UniProtKB'
        name = element.attrib['type']
        description = None
        position = element.find('location/position')
        if position is None:
            start = int(element.find('location/begin').attrib['position']) - 1
            length = int(element.find('location/end').attrib['position']) - start
        else:
            start = int(position.attrib['position']) - 1
            length = 1
        region = Region(start, length)
        original_description = element.attrib.get('description', None)
        attrib_order = ['status', 'evidence', 'id', 'ref']
        d = dict((a, element.attrib.get(a, None)) for a in attrib_order)
        d['original'] = element.find('original')
        if d['original'] is not None:
            d['original'] = d['original'].text
        d['variation'] = element.find('variation')
        if d['variation'] is not None:
            d['variation'] = d['variation'].text
        desc = []
        if original_description and not original_description.startswith('('):
            desc.append(original_description)
        if d['original']:
            variation = "%s->%s" % (d['original'], d['variation'])
            desc.append(variation)
        attrs = ["%s=%s" % (a, d[a]) for a in attrib_order[:-2] if d[a]]
        if attrs:
            desc.append(', '.join(attrs))
        if desc:
            description = '; '.join(desc)
        return cls(source=source, name=name, region=region, description=description, **d)

def get_uniprot_features(uniprot_etree_entry, msa):
    offset = uniprot_etree_entry.offset or 0
    if uniprot_etree_entry.root is None:
        return []
    features = []
    for element in uniprot_etree_entry.root.findall('feature'):
        feature = UniprotSequenceFeature.from_element(element)
        feature.sequence_index = uniprot_etree_entry.sequence_index
        feature.sequence_id = uniprot_etree_entry.sequence_id
        feature.map_to_msa(msa, offset)
        if not feature.mapping:
            continue
        features.append(feature)
    return features
    
class ImportUniprotFeatures(Action):
    action_name = 'import-uniprot-features'
    path = ['Import', 'Sequence features', 'UniProtKB annotations']
    tooltip = 'Import feature annotations for all UniProtKB sequences.'
    
    batch_size = 10
    
    @classmethod
    def applicable(cls, target, coord=None):
        if target.msaview_classname != 'data.msa':
            return
        if not target:
            return
        if ('uniprot-etree' in target.sequence_information.categories or
            'uniprot-ids' in target.sequence_information.categories):
            return cls(target, coord)  
        for id in target.ids:
            if UniprotID.extract_id(id):
                return cls(target, coord)

    def run(self):
        id_entries = get_populated_uniprot_id_category(self.target)
        etree_entries = self.target.sequence_information.setdefault('uniprot-etree')
        features = []
        id_enumeration = []
        for sequence_index, etree_entry in enumerate(etree_entries):
            if etree_entry is not None:
                features.extend(get_uniprot_features(etree_entry, self.target))
                continue
            id_entry = id_entries[sequence_index]
            sequence_id = (id_entry and id_entry.sequence_id)
            if sequence_id:
                id_enumeration.append((sequence_index, sequence_id))
        self.target.features.add_features(features)
        task = UniprotXMLDownloadTask(self.target, id_enumeration, self.batch_size)
        def add_new_features(t, progress, finished, entries):
            for entry in entries or []:
                new_features = get_uniprot_features(entry, self.target)
                self.target.features.add_features(new_features)
        task.connect('progress', add_new_features)
        task.connect('progress', lambda t, progress, finished, entries: self.target.sequence_information.add_entries(entries or []))
        self.target.sequence_information.connect('changed', task.handle_id_category_changed)
        self.target.get_compute_manager().timeout_add(100, task)
        return task

register_action(ImportUniprotFeatures)

class ImportUniprotFeaturesForSequence(Action):
    action_name = 'import-uniprot-features-for-sequence'
    path = ['Import', 'Sequence features', 'UniProtKB annotations (single sequence)']
    tooltip = 'Import feature annotations for the sequence from UniProtKB.'
    
    @classmethod
    def applicable(cls, target, coord=None):
        if not coord or coord.sequence is None:
            return
        if target.msaview_classname != 'data.msa':
            return
        if (target.sequence_information.get_entry('uniprot-etree', coord.sequence) or
            target.sequence_information.get_entry('uniprot-id', coord.sequence)):
            return cls(target, coord)
        if UniprotID.extract_id(target.ids[coord.sequence]):
            return cls(target, coord)
    
    def run(self):
        sequence_index = self.coord.sequence
        etree_category = self.target.sequence_information.setdefault('uniprot-etree')
        entry = etree_category[sequence_index]
        if entry is None:
            entry = dbfetch_uniprot_xml_for_sequence(self.target, sequence_index)
            if not entry:
                return
            self.target.sequence_information.add_entries(entry)
        if entry.root is None:
            return
        features = get_uniprot_features(entry, self.target)
        self.target.features.add_features(features)

register_action(ImportUniprotFeaturesForSequence)

class ShowSequenceInUniprotWebInterface(Action):
    action_name = 'show-sequence-in-uniprot-web-interface'
    path = ['Web interface', 'UniProtKB', 'Show protein view for %r']
    tooltip = 'Show sequence in the UniProtKB web interface.'
    
    url = 'http://www.uniprot.org/uniprot/' 
    
    @classmethod
    def applicable(cls, target, coord=None):
        if not coord or coord.sequence is None:
            return
        if target.msaview_classname != 'data.msa':
            return
        entry = target.sequence_information.get_entry('uniprot-id', coord.sequence)
        if not entry:
            entry = UniprotID.from_msa_sequence(target, coord.sequence)
        if not entry.sequence_id:
            return
        a = cls(target, coord)
        a.path = list(cls.path)
        a.path[-1] %= entry.sequence_id
        return a
    
    def run(self):
        sequence_index = self.coord.sequence
        entry = get_id_entry_for_sequence(self.target, sequence_index)
        gio.app_info_get_default_for_uri_scheme('http').launch_uris([self.url + entry.sequence_id])

register_action(ShowSequenceInUniprotWebInterface)

class ImportUniprotXML(Action):
    action_name = 'import-uniprot-xml'
    path = ['Import', 'Sequence information', 'Download UniProtKB XML']
    tooltip = 'Download UniProtKB XML data for all sequences.'
    
    batch_size = 50
    
    @classmethod
    def applicable(cls, target, coord=None):
        if target.msaview_classname != 'data.msa':
            return
        if not target:
            return
        if 'uniprot-ids' in target.sequence_information.categories:
            return cls(target, coord)  
        for id in target.ids:
            if UniprotID.extract_id(id):
                return cls(target, coord)

    def run(self):
        id_entries = get_populated_uniprot_id_category(self.target)
        etree_entries = self.target.sequence_information.setdefault('uniprot-etree')
        id_enumeration = []
        for sequence_index, etree_entry in enumerate(etree_entries):
            if etree_entry is not None:
                continue
            id_entry = id_entries[sequence_index]
            sequence_id = (id_entry and id_entry.sequence_id)
            if sequence_id:
                id_enumeration.append((sequence_index, sequence_id))
        task = UniprotXMLDownloadTask(self.target, id_enumeration, self.batch_size)
        task.connect('progress', lambda t, progress, finished, entries: self.target.sequence_information.add_entries(entries or []))
        self.target.sequence_information.connect('changed', task.handle_id_category_changed)
        self.target.get_compute_manager().timeout_add(100, task)
        return task

register_action(ImportUniprotXML)

class ImportUniprotXMLForSequence(Action):
    action_name = 'import-uniprot-xml-for-sequence'
    path = ['Import', 'Sequence information', 'Download UniProtKB XML (single sequence)']
    tooltip = 'Download UniProtKB XML data for the sequence.'
    
    url = 'http://www.uniprot.org/uniprot/' 

    @classmethod
    def applicable(cls, target, coord=None):
        if not coord or coord.sequence is None:
            return
        if target.msaview_classname != 'data.msa':
            return
        entry = target.sequence_information.get_entry('uniprot-id', coord.sequence)
        if not entry:
            entry = UniprotID.from_msa_sequence(target, coord.sequence)
        if not entry.sequence_id:
            return
        return cls(target, coord)

    def run(self):
        sequence_index = self.coord.sequence
        self.target.sequence_information.setdefault('uniprot-etree')
        etree_entry = dbfetch_uniprot_xml_for_sequence(self.target, sequence_index)
        self.target.sequence_information.add_entries(etree_entry)
        
register_action(ImportUniprotXMLForSequence)

class SaveUniprotXML(Action):
    action_name = 'save-uniprot-xml'
    path = ['Export', 'Sequence information', 'UniProtKB XML']
    tooltip = 'Save UniProtKB XML data.'
    
    uniprot_xml_declaration = """<?xml version="1.0" encoding="UTF-8"?>"""
    uniprot_xml_root_element = """<uniprot xmlns="http://uniprot.org/uniprot" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://uniprot.org/uniprot http://www.uniprot.org/support/docs/uniprot.xsd"/>"""
    
    @classmethod
    def applicable(cls, target, coord=None):
        if target.msaview_classname != 'data.msa':
            return
        try:
            (True for e in target.sequence_information.categories.get('uniprot-etree', []) if (e and e.root)).next()
        except StopIteration:
            return
        return cls(target, coord)
    
    def get_options(self):
        path = 'uniprot.xml'
        if self.target and self.target.path:
            path = self.target.path + '.uniprot.xml'
        return [Option(None, 'path', path, path, 'Path', 'Where to save the UniProtKB XML data.')]

    def run(self):
        root = etree.XML(self.uniprot_xml_root_element)
        tree = etree.ElementTree(root)
        for entry in self.target.sequence_information.categories['uniprot-etree']:
            if not (entry and entry.root):
                continue
            root.append(entry.root)
        f = open(self.params['path'], 'w')
        tree.write(f)
        f.close()
        
register_action(ImportUniprotXMLForSequence)

