import gzip
import os

from msaview.action import (Action,
                            register_action)
from msaview.options import Option

class StockholmFormatMSA(object):
    def __init__(self, sequences=None, ids=None, descriptions=None):
        self.sequences = sequences
        self.ids = ids
        self.descriptions = descriptions

    @classmethod
    def from_text(cls, msa):
        sequences = []
        ids = []
        descr = {}
        for line in msa:
            if not line.strip():
                continue
            if line.startswith('#=GS'):
                id, type, description = line.split(None, 3)[1:]
                if type == 'DE':
                    descr[id] = description.strip()
                continue
            if line.startswith('#'):
                continue
            if line.startswith('//'):
                break
            id, sequence = line.split(None, 1)
            ids.append(id)
            sequences.append(sequence.strip())
        descriptions = [descr.get(id, '') for id in ids]
        return cls(sequences, ids, descriptions)

    @classmethod
    def format_stockholm_msa(cls, ids, sequences, descriptions):
        out = ['# STOCKHOLM 1.0']
        out.append('#=GF SQ   %s' % len(ids))
        id_width = max(len(id) for id in ids)
        for id, description in zip(ids, descriptions):
            if description:
                out.append("#=GS %-*s DE %s" % (id_width + 1, id, description))
        for id, sequence in zip(ids, sequences):
            out.append("%-*s %s" % (id_width + 12, id, sequence))
        return '\n'.join(out)

class ReadStockholmMSA(Action):
    action_name = 'open-stockholm-alignment'
    path = ['Open', 'Stockholm format alignment']
    tooltip = 'Read a Stockholm format alignment file.'

    @classmethod
    def applicable(cls, target=None, coord=None):
        if target.msaview_classname == 'data.msa':
            return cls(target)

    def get_options(self):
        return [Option(propname='location', default='', value='', nick='Location', tooltip='The alignment file to read.')]

    def run(self):
        if self.params['location'].endswith('.gz'):
            alignment = gzip.GzipFile(self.params['location'])
        else:
            alignment = open(self.params['location'])
        msa = StockholmFormatMSA.from_text(alignment)
        self.target.set_msa(msa.sequences, self.params['location'], msa.ids, msa.descriptions)
    
register_action(ReadStockholmMSA)

class SaveStockholmMSA(Action):
    action_name = 'save-stockholm-alignment'
    path = ['Save', 'Stockholm format alignment']
    tooltip = 'Save the alignment in Stockholm format.'

    @classmethod
    def applicable(cls, target=None, coord=None):
        if target.msaview_classname == 'data.msa':
            return cls(target)

    def get_options(self):
        try:
            path = os.path.splitext(self.target.path)[0] + '.stockholm'
        except:
            path = ''
        return [Option(propname='location', default=path, value=path, nick='Location', tooltip='Where to save the alignment. End with .gz to save a compressed MSA.')]

    def run(self):
        if self.params['location'].endswith('.gz'):
            alignment = gzip.GzipFile(self.params['location'], 'w')
        else:
            alignment = open(self.params['location'], 'w')
        alignment.write(StockholmFormatMSA.format_stockholm_msa(self.target.ids, self.target.sequences, self.target.descriptions))
        self.target.path = self.params['location']
    
register_action(SaveStockholmMSA)

class SaveCopyStockholmMSA(Action):
    action_name = 'save-copy-stockholm-alignment'
    path = ['Save', 'Stockholm format alignment (copy)']
    tooltip = 'Save a copy of the alignment in Stockholm format.'

    @classmethod
    def applicable(cls, target=None, coord=None):
        if target.msaview_classname == 'data.msa':
            return cls(target)

    def get_options(self):
        try:
            path = os.path.splitext(self.target.path)[0] + '.stockholm'
        except:
            path = ''
        return [Option(propname='location', default=path, value=path, nick='Location', tooltip='Where to save the alignment. End with .gz to save a compressed MSA.')]

    def run(self):
        if self.params['location'].endswith('.gz'):
            alignment = gzip.GzipFile(self.params['location'], 'w')
        else:
            alignment = open(self.params['location'], 'w')
        alignment.write(StockholmFormatMSA.format_stockholm_msa(self.target.ids, self.target.sequences, self.target.descriptions))
    
register_action(SaveCopyStockholmMSA)
