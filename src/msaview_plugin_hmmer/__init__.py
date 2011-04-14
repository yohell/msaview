__version__ = "0.9.0"

import os

from msaview import presets
from msaview.action import (Action,
                            register_action)
from msaview.features import (SequenceFeature,
                              map_region_to_msa)
from msaview.options import Option
from msaview.selection import Region
from msaview.sequence_information import get_id_index

class HMMERDomainHit(SequenceFeature):
    def __init__(self, sequence_index=None, sequence_id=None, source=None, name=None, region=None, mapping=None, description=None, accession=None, termini=None, hmm_region=None, hmm_termini=None, score=None, evalue=None):
        self.sequence_index = sequence_index
        self.sequence_id = sequence_id
        self.source = source
        self.name = name
        self.region = region
        self.mapping = mapping
        self.description = description
        self.accession = accession
        self.termini = termini
        self.hmm_region = hmm_region
        self.hmm_termini = hmm_termini
        self.score = score
        self.evalue = evalue
        
    @classmethod
    def from_hitline(cls, line, name='', accession=None, description=None):
        """This is what we're parsing:
         sp|Q7TVK8|PHAS_MYCBO    1/1    1453  1714 ..     1   272 []   341.1  8.7e-98
        (Sequence              Domain  seq-f seq-t sc hmm-f hmm-t hc   score  E-value)
        """
        words = line.split()
        start = int(words[2]) - 1
        hmm_start = int(words[5]) - 1
        return cls(sequence_id = words[0],
                   source="HMMER",
                   name=name,
                   region=Region(start, int(words[3]) - start),
                   description=description,
                   accession=accession,
                   termini=tuple(s != '.' for s in words[4]),
                   hmm_region=Region(hmm_start, int(words[6]) - hmm_start),
                   hmm_termini=tuple(s != '.' for s in words[7]),
                   score = float(words[-2]),
                   evalue = float(words[-1]))

    def to_str(self):
        description = ''
        if self.description:
            description = self.description + " "
        template = "%s %s-%s %se-value=%s score=%s" 
        return template % (self.name, 
                           self.region.start + 1, 
                           self.region.start + self.region.length, 
                           description, 
                           self.evalue, 
                           self.score)
    
    def to_markup(self, color=presets.get_value('color:black')):
        """Return markup appropriate for a tooltip.
        
        color can optionally be applied to a pertinent segment of the returned markup.
        
        """
        template = "<span foreground=%r weight='bold'>%s</span> %s-%s evalue=%s score=%s"
        markup = template % (color.to_str(), self.name.replace('<', '&lt;'), self.region.start, self.region.start + self.region.length, self.evalue, self.score)
        if self.description:
            markup += " (%s)" % self.description
        return markup

def iter_domains(hmmsearch_file):
    hmm = ''
    for line in hmmsearch_file:
        if line.startswith('Query HMM:'):
            name = line[len('Query HMM:'):].strip()
        if line.startswith('Accession:'):
            ac = line[len('Accession:'):].strip()
            if ac == '[none]':
                ac = None
        if line.startswith('Description:'):
            description = line[len('Description:'):].strip()
            if description == '[none]':
                description = None
        if line.startswith('Parsed for domains:'):
            break
    # Skip past 2 more header lines:
    hmmsearch_file.next()
    hmmsearch_file.next()
    for line in hmmsearch_file:
        if line[0].isspace():
            break
        yield HMMERDomainHit.from_hitline(line, name=name, accession=ac, description=description)
    if not os.path.isfile(hmmsearch_file.name):
        for line in hmmsearch_file:
            pass

class ImportHMMSearchResults(Action):
    action_name = 'import-hmmsearch-domains'
    path = ['Import', 'Sequence features', 'hmmsearch domains']
    tooltip = 'Import domain hits from a hmmsearch result file.'
    
    @classmethod
    def applicable(cls, target, coord=None):
        if target.msaview_classname == 'data.msa':
            return cls(target.features)
        if target.msaview_classname == 'data.sequence_features':
            return cls(target)
    
    def get_options(self):
        path = ''
        if self.target and self.target.msa.path:
            path = self.target.msa.path + '.hmmsearch'
        return [Option(propname='location', default=path, value=path, nick='Location', tooltip='The hmmsearch result file to parse.')]

    def run(self):
        features = []
        for feature in iter_domains(open(self.params['location'])):
            feature.sequence_index = get_id_index(self.target.msa.ids, feature.sequence_id)
            if feature.sequence_index is None:
                continue
            feature.mapping = map_region_to_msa(feature.region, self.target.msa.msa_positions[feature.sequence_index])
            if feature.mapping is None:
                continue
            features.append(feature)
        self.target.add_features(features)

    
register_action(ImportHMMSearchResults)

#presets.add_to_preset_path(__file__)

