"""MSAView - Pfam support.

Copyright (c) 2011 Joel Hedlund.

Contact: Joel Hedlund <yohell@ifm.liu.se>

MSAView is a modular, configurable and extensible package for analysing and 
visualising multiple sequence alignments and sequence features. 

This package provides support for querying and retrieving data from Pfam, 
including alignments and domain annotations. 
 
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

import gzip
import StringIO
import urllib2
from xml.etree import ElementTree as etree

import gio

from msaview.action import (Action,
                            register_action)
from msaview.computation import (DownloadTask,
                                 NamespaceIgnorantXMLTreeBuilder,
                                 SimpleETreeDownloader)
from msaview.features import map_region_to_msa
from msaview.options import (BooleanOption, 
                             Option)
from msaview.selection import Region

from msaview_plugin_hmmer import HMMERDomainHit
from msaview_plugin_stockholm import StockholmFormatMSA
from msaview_plugin_uniprot import (UniprotID,
                                    get_id_entry_for_sequence,
                                    get_populated_uniprot_id_category)

class DownloadPfamAlignment(Action):
    action_name = 'download-pfam-alignment'
    path = ['Open', 'Download Pfam alignment']
    tooltip = 'Download a Pfam family alignment from the Pfam website.'

    @classmethod
    def applicable(cls, target=None, coord=None):
        if target.msaview_classname == 'data.msa':
            return cls(target)

    def get_options(self):
        return [Option(propname='id', default='', value='', nick='Pfam ID', tooltip='The Pfam ID for the family.'),
                BooleanOption(propname='full', default=False, value=False, nick='Full Alignment', tooltip='Retrieve the full alignment instead of just the seed.')]

    def run(self):
        url = "http://pfam.sanger.ac.uk/family/alignment/download/gzipped?acc=%s&alnType=%s"
        url %= self.params['id'], ('full' if self.params['full'] else 'seed') 
        tmp = StringIO.StringIO(urllib2.urlopen(url).read())
        alignment = gzip.GzipFile(fileobj=tmp)
        msa = StockholmFormatMSA.from_text(alignment)
        path = "%s-%s" % (self.params['id'], ('full' if self.params['full'] else 'seed'))
        self.target.set_msa(msa.sequences, path, msa.ids, msa.descriptions)
   
register_action(DownloadPfamAlignment)
 
class OpenPfamAlignment(Action):
    action_name = 'open-pfam-alignment'
    path = ['Open', 'Pfam alignment']
    tooltip = 'Open a Pfam family alignment from the Pfam website.'

    @classmethod
    def applicable(cls, target=None, coord=None):
        if target.msaview_classname == 'data.msa':
            return cls(target)

    def get_options(self):
        return [Option(propname='location', default='', value='', nick='Location', tooltip='The alignment file to read.')]

    def run(self):
        msa = StockholmFormatMSA.from_text(open(self.params['location']))
        self.target.set_msa(msa.sequences, self.params['location'], msa.ids, msa.descriptions)
    
register_action(OpenPfamAlignment)

class PfamDomain(HMMERDomainHit):
    @classmethod
    def from_pfam_match_etree(cls, match_element, msa, sequence_index, offset, sequence_id=None):
        loc = match_element.find('location')
        start = int(loc.attrib['start']) - 1
        region = Region(start, int(loc.attrib['end']) - start)
        mapping = map_region_to_msa(region, msa.msa_positions[sequence_index], offset)
        if not mapping:
            return None
        hmm_start = int(loc.attrib['hmm_start']) - 1
        return cls(sequence_index=sequence_index,
                   sequence_id=sequence_id,
                   source=match_element.attrib['type'],
                   name=match_element.attrib['id'],
                   region=region,
                   mapping=mapping,
                   accession=match_element.attrib['accession'],
                   hmm_region=Region(hmm_start, int(loc.attrib['hmm_end']) - hmm_start),
                   score=float(loc.attrib['bitscore']),
                   evalue=float(loc.attrib['evalue']))

def parse_pfam_protein_etree(root, msa, sequence_index, sequence_id=None):
    sequence = root.find('entry/sequence').text.strip()
    offset = sequence.find(msa.unaligned[sequence_index])
    if offset < 0:
        return None
    features = []
    for element in root.findall('entry/matches/match'):
        feature = PfamDomain.from_pfam_match_etree(element, msa, sequence_index, offset, sequence_id)
        if feature:
            features.append(feature)
    return features
    
"""
Hi all! I'm writing a module for a pygtk app, and at one point I'll need to determine whether or not gobject.threads_init() has already been called. If it has, then I can use threads to avoid blocking while waiting for network traffic to finish, but if it hasn't then my threads won't do anything and the user will wait forever for the results. Is this possible using pygtk? I saw C glib has a function bool g_thread_supported() that supposedly does just that, but does pygtk have anything similar?

are there any negative aspects of calling gobject.threads_init()? That is, if I put that at the start of my module, would I potentially break stuff for some people that use my module?

"""    
class PfamDomainDownloadTask(DownloadTask):
    url = 'http://pfam.sanger.ac.uk/protein?output=xml&entry=%s'
    downloader_class = SimpleETreeDownloader

    def process_downloads(self, data):
        features = []
        for i, tree in enumerate(data):
            root = tree.getroot()
            sequence_index, sequence_id = self.id_enumeration[self.progress + i]
            new_features = parse_pfam_protein_etree(root, self.msa, sequence_index, sequence_id)
            if new_features:
                features.extend(new_features)
        return features
    
    def handle_id_category_changed(self, sequence_information, change):
        if change.has_changed('uniprot-id'):
            self.abort()

class ImportPfamDomains(Action):
    action_name = 'import-pfam-domains'
    path = ['Import', 'Sequence features', 'Pfam domains']
    tooltip = 'Download Pfam domain annotations for all UniProtKB sequences in the MSA.'

    batch_size = 10
    
    @classmethod
    def applicable(cls, target=None, coord=None):
        if target.msaview_classname != 'data.msa':
            return
        if not target:
            return
        if target.sequence_information.has_category('uniprot-id'):
            return cls(target, coord)
        for id in target.ids:
            if UniprotID.extract_id(id):
                return cls(target, coord)

    def run(self):
        entries = get_populated_uniprot_id_category(self.target)
        id_enumeration = [(i, entry.sequence_id) for i, entry in enumerate(entries) if (entry and entry.sequence_id) is not None]
        task = PfamDomainDownloadTask(self.target, id_enumeration, self.batch_size)
        m = self.target.find_ancestor('msaview')
        task.connect('progress', lambda t, progress, finished, features: self.target.features.add_features(features or []))
        self.target.sequence_information.connect('changed', task.handle_id_category_changed)
        self.target.get_compute_manager().timeout_add(100, task)
        return task

register_action(ImportPfamDomains)    

class ImportPfamDomainsForUniprotSequence(Action):
    action_name = 'import-pfam-domains-for-uniprot-sequence'
    path = ['Import', 'Sequence features', 'Pfam domains (single UniProtKB sequence)']
    tooltip = 'Download Pfam domain annotations for a UniProtKB sequence.'

    @classmethod
    def applicable(cls, target=None, coord=None):
        if not coord or coord.sequence is None:
            return
        if target.msaview_classname != 'data.msa':
            return
        if target.sequence_information.get_entry('uniprot-id', coord.sequence):
            return cls(target, coord)
        if UniprotID.extract_id(target.ids[coord.sequence]):
            return cls(target, coord)

    def run(self):
        sequence_index = self.coord.sequence
        id = self.target.sequence_information.setdefault('uniprot-id')[sequence_index]
        if not id:
            id = UniprotID.from_msa_sequence(self.target, sequence_index)
            self.target.sequence_information.add_entries(id)
        url = 'http://pfam.sanger.ac.uk/protein?output=xml&entry='
        xml = urllib2.urlopen(url + id.sequence_id)
        root = etree.parse(xml, NamespaceIgnorantXMLTreeBuilder()).getroot()
        features = parse_pfam_protein_etree(root, self.target, sequence_index, id.sequence_id)
        if features is None:
            raise ValueError('the Pfam sequence does not match/contain the MSA sequence')
        self.target.features.add_features(features)

register_action(ImportPfamDomainsForUniprotSequence)    

class ShowSequenceInPfamWebInterface(Action):
    action_name = 'show-sequence-in-pfam-web-interface'
    path = ['Web interface', 'Pfam', 'Show sequence view for %r']
    tooltip = 'Show sequence in the Pfam web interface.'
    
    url = 'http://pfam.sanger.ac.uk/protein/' 
    
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

register_action(ShowSequenceInPfamWebInterface)

class ShowDomainInPfamWebInterface(Action):
    action_name = 'show-domain-in-pfam-web-interface'
    path = ['Web interface', 'Pfam', 'Show domain view for %r']
    tooltip = 'Show domain in the Pfam web interface.'
    
    url = 'http://pfam.sanger.ac.uk/family/' 
    
    @classmethod
    def applicable(cls, target, coord=None):
        if (not coord or 
            coord.position is None or
            coord.sequence is None):
            return
        if target.msaview_classname != 'data.msa':
            return
        feature = target.features.find(lambda f: f.source.startswith('Pfam') and coord.position in f.mapping, coord.sequence)
        if not feature:
            return
        a = cls(target, coord)
        a.path = list(cls.path)
        a.path[-1] %= feature.name
        a.params['name'] = feature.name
        return a
    
    def run(self):
        gio.app_info_get_default_for_uri_scheme('http').launch_uris([self.url + self.params['name']])

register_action(ShowDomainInPfamWebInterface)

