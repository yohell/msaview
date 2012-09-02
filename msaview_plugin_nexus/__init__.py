"""MSAView - Nexus support.

Copyright (c) 2011 Joel Hedlund.

Contact: Joel Hedlund <yohell@ifm.liu.se>

MSAView is a modular, configurable and extensible package for analysing and 
visualising multiple sequence alignments and sequence features. 

This package provides read/write support Nexus style alignments. 
 
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

import os

import re

from msaview.action import (Action,
                            register_action)
from msaview.options import (BooleanOption,
                             Option)

class NexusFormatMSA(object):
    def __init__(self, sequences=None, ids=None):
        self.sequences = sequences
        self.ids = ids

    @classmethod
    def from_text(cls, msa):
        sequences = []
        ids = []
        msa = iter(msa)
        for line in msa:
            if re.match(r'\s*Begin\s+data\s*;', line, re.IGNORECASE):
                break
        else:
            return None
        for line in msa:
            if re.match(r'\s*Matrix', line, re.IGNORECASE):
                break
        else:
            return None
        i = 0
        for line in msa:
            words = line.split()
            if words[0] == ';':
                break
            if not words:
                i = 0
                continue
            id = words.pop(0)
            part = ''.join(words)
            if i >= len(sequences):
                ids.append(id)
                sequences.append([])
            sequences[i].append(part)
            i += 1
        sequences = tuple(''.join(l) for l in sequences)
        return cls(sequences, ids)

    @classmethod
    def format_nexus_msa(cls, ids, sequences, nucleic=False, interleave_length=0):
        out = ['#NEXUS\n\nBegin data;']
        out.append('Dimensions ntax=%d nchar=%d;' % (len(ids), len(sequences[0])))
        datatype = 'dna' if nucleic else 'protein'
        interl = ' interleave' if interleave_length else ''
        out.append('Format datatype=%s%s gap= -;' % (datatype, interl))
        out.append('Matrix')
        id_width = max(len(s) for s in ids)
        length = interleave_length or len(sequences[0])
        for i in range(0, len(sequences[0]), length):
            for id, sequence in zip(ids, sequences):
                out.append('%-*s %s' % (id_width, id, sequence[i:i+length]))
            if i + length < len(sequences[0]):
                out.append('')
        out.append(';')
        out.append('End;')
        return '\n'.join(out)

    def to_str(self):
        return self.format_clustal_msa(self.ids, self.sequences)

class ReadNexusMSA(Action):
    action_name = 'open-nexus-alignment'
    path = ['Open', 'Nexus format alignment']
    tooltip = 'Read a Nexus format alignment file.'

    @classmethod
    def applicable(cls, target=None, coord=None):
        if target.msaview_classname == 'data.msa':
            return cls(target)

    def get_options(self):
        return [Option(propname='location', default='', value='', nick='Location', tooltip='The alignment file to read.')]

    def run(self):
        msa = NexusFormatMSA.from_text(open(self.params['location']))
        self.target.set_msa(msa.sequences, self.params['location'], msa.ids)
    
register_action(ReadNexusMSA)

class SaveCopyNexusMSA(Action):
    action_name = 'save-copy-nexus-alignment'
    path = ['Save', 'Nexus alignment (copy)']
    tooltip = 'Save a copy of the alignment in Nexus format.'

    @classmethod
    def applicable(cls, target=None, coord=None):
        if target.msaview_classname == 'data.msa' and target.sequences:
            return cls(target)

    def get_options(self):
        try:
            path = os.path.splitext(self.target.path)[0] + '.nxs'
        except:
            path = ''
        return [Option(propname='location', default=path, value=path, nick='Location', tooltip='Where to save the alignment.'),
                BooleanOption(propname='interleave', default=True, value=True, nick='Interleaved', tooltip='Break up alignment Clustal style or save one sequence per line.'),
                Option(propname='datatype', default='protein', value='auto', nick='Data type', tooltip='Sequence type, protein or DNA. Auto means DNA if more than 90% of the first 1000 letters are A, T, C or G.')]

    def run(self):
        if self.params['datatype'].strip().lower() == 'auto':
            counts = dict()
            total = 0
            for seq in self.target.unaligned:
                for letter in seq.lower():
                    total += 1
                    if letter in counts:
                        counts[letter] += 1
                        continue
                    counts[letter] = 1
                    if total >= 1000:
                        break
                if total >= 1000:
                    break
            atcg = sum(counts.get(letter, 0) for letter in 'atcg')
            if float(atcg) / total:
                self.params['datatype'] = 'DNA'
            else:
                self.params['datatype'] = 'protein'
        alignment = open(self.params['location'], 'w')
        alignment.write(NexusFormatMSA.format_nexus_msa(self.target.ids, self.target.sequences, self.params['datatype'].lower() == 'protein', (60 if self.params['interleave'] else 0)))
    
register_action(SaveCopyNexusMSA)

class SaveNexusMSA(SaveCopyNexusMSA):
    action_name = 'save-nexus-alignment'
    path = ['Save', 'Nexus alignment']
    tooltip = 'Save the alignment in Nexus format.'

    def run(self):
        SaveCopyNexusMSA.run(self)
        self.target.path = self.params['location']
    
register_action(SaveNexusMSA)
