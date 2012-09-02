"""MSAView - PDB support.

Copyright (c) 2011 Joel Hedlund.

Contact: Joel Hedlund <yohell@ifm.liu.se>

MSAView is a modular, configurable and extensible package for analysing and 
visualising multiple sequence alignments and sequence features. 

This package provides support for detecting PDB links in uniprot entries, 
and pointing the default web browser to the PDB web interface for additional
details. 
 
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

import gio

from msaview.action import (Action,
                            register_action)
from msaview.sequence_information import SequenceInformation

from msaview_plugin_uniprot import (UniprotID,
                                    dbfetch_uniprot_xml_for_sequence)

class StructureInformation(object):
    def __init__(self, id=None, method=None, resolution=None, chains=None):
        self.id = id
        self.method = method
        self.resolution = resolution
        self.chains = chains
    
    @classmethod
    def from_pdb_reference(cls, element):
        id = element.attrib['id']
        # get property values for method, resolution and chains
        properties = dict((e.attrib['type'], e.attrib['value']) for e in element.findall('property'))
        properties['resolution'] = float(properties['resolution'].strip(' A'))
        return cls(id, **properties) 

    @classmethod
    def from_uniprot_etree(cls, root):
        structures = []
        for element in root.findall('dbReference'):
            if element.attrib.get('type', None) != 'PDB':
                continue
            structures.append(cls.from_pdb_reference(element))
        return structures
    
class PDBStructures(SequenceInformation):
    category = 'pdb-ids'
    def __init__(self, sequence_index, sequence_id=None, structures=None):
        self.sequence_index = sequence_index
        self.sequence_id = sequence_id
        if structures is None:
            structures = []
        self.structures = structures
        
    @classmethod
    def from_uniprot_etree(cls, entry):
        if (entry and entry.root) is None:
            return
        sequence_index = entry.sequence_index
        sequence_id = entry.sequence_id
        structures = StructureInformation.from_uniprot_etree(entry.root)
        return cls(sequence_index, sequence_id, structures)
    
def get_populated_pdb_ids_category(msa):
    pdb_ids_category = msa.sequence_information.setdefault('pdb-ids')
    new_entries = []
    for i, etree_entry in enumerate(msa.sequence_information.categories.get('uniprot-etree', [])):
        if pdb_ids_category[i]:
            continue
        entry = PDBStructures.from_uniprot_etree(etree_entry)
        if entry:
            new_entries.append(entry)
    msa.sequence_information.add_information(new_entries)
    return pdb_ids_category
    
class FindPDBStructuresForUniprotSequences(Action):
    action_name = 'find-pdb-structures'
    path = ['Import', 'Sequence information', 'Find PDB structure links']
    tooltip = 'Extract PDB structure links from already imported UniProtKB XML data.'
    
    @classmethod
    def applicable(cls, target, coord=None):
        if target.msaview_classname != 'data.msa':
            return
        etree_category = target.sequence_information.categories.get('uniprot-etree', [None])
        try:
            (e for e in etree_category if (e and e.root) is not None).next()
        except StopIteration:
            return
        return cls(target, coord)

    def run(self):
        pdb_ids_category = self.target.sequence_information.setdefault('pdb-ids')
        new_entries = []
        for i, etree_entry in enumerate(self.target.sequence_information.categories['uniprot-etree']):
            if pdb_ids_category[i]:
                continue
            pdb_ids_entry = PDBStructures.from_uniprot_etree(etree_entry)
            if pdb_ids_entry:
                new_entries.append(pdb_ids_entry)
        self.target.sequence_information.add_entries(new_entries)
        
register_action(FindPDBStructuresForUniprotSequences)
    
class ImportPDBStructuresForUniprotSequence(Action):
    action_name = 'import-pdb-structures-for-sequence'
    path = ['Import', 'Sequence information', 'Download PDB structure links (single sequence)']
    tooltip = 'Download PDB structure links from UniProtKB XML data for the sequence.'
    
    url = 'http://www.uniprot.org/uniprot/' 

    @classmethod
    def applicable(cls, target, coord=None):
        if not coord or coord.sequence is None:
            return
        if target.msaview_classname != 'data.msa':
            return
        etree_entry = target.sequence_information.get_entry('uniprot-etree', coord.sequence)
        if etree_entry:
            if etree_entry.root is None:
                return
            return cls(target, coord)
        id_entry = target.sequence_information.get_entry('uniprot-id', coord.sequence)
        if not id_entry:
            id_entry = UniprotID.from_msa_sequence(target, coord.sequence)
        if not id_entry.sequence_id:
            return
        return cls(target, coord)

    def run(self):
        sequence_index = self.coord.sequence
        etree_category = self.target.sequence_information.setdefault('uniprot-etree')
        etree_entry = etree_category[sequence_index]
        if not etree_entry:
            id_category = self.target.sequence_information.setdefault('uniprot-id')
            id_entry = id_category[sequence_index]
            if not id_entry:
                id_entry = UniprotID.from_msa_sequence(self.target, self.coord.sequence)
                self.target.sequence_information.add_entries(id_entry)
            etree_entry = dbfetch_uniprot_xml_for_sequence(self.target, sequence_index)
            self.target.sequence_information.add_entries(etree_entry)
        structures_entry = PDBStructures.from_uniprot_etree(etree_entry)
        self.target.sequence_information.setdefault('pdb-ids')
        self.target.sequence_information.add_entries(structures_entry)
        
register_action(ImportPDBStructuresForUniprotSequence)
    
class ShowStructureInPDBWebInterface(Action):
    action_name = 'show-structure-in-pdb-web-interface'
    path = ['Web interface', 'PDB', 'Show structure for %s']
    tooltip = 'Show structure in the PDB web interface.'
    
    url = 'http://www.rcsb.org/pdb/explore.do?structureId=' 
    
    @classmethod
    def applicable(cls, target, coord=None):
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
    
    def run(self):
        structure = self.params['structure']
        gio.app_info_get_default_for_uri_scheme('http').launch_uris([self.url + structure.id])

register_action(ShowStructureInPDBWebInterface)
    