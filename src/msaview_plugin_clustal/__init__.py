"""MSAView - Clustal support.

Copyright (c) 2011 Joel Hedlund.

Contact: Joel Hedlund <yohell@ifm.liu.se>

MSAView is a modular, configurable and extensible package for analysing and 
visualising multiple sequence alignments and sequence features. 

This package provides read/write support for Clustal like alignments. 
 
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

from msaview.action import (Action,
                            register_action)
from msaview.options import Option

class ClustalFormatMSA(object):
    def __init__(self, sequences=None, ids=None):
        self.sequences = sequences
        self.ids = ids

    @classmethod
    def from_text(cls, msa):
        sequences = []
        ids = []
        msa = iter(msa)
        msa.next() # throw away this header line : CLUSTAL 2.0.10 multiple sequence alignment
        msa.next() # and throw away the following two blank lines...
        msa.next() 
        i = 0
        for line in msa:
            if not line[0].isspace():
                # Conservation annotation and blank line after block end.
                msa.next()
                i = 0
                continue
            id, sequence = line.split()
            if i == len(ids):
                ids.append(id)
                sequences.append('')
            if id != ids[i]:
                raise ValueError('inconsistent ids for sequence %s (%r vs %r)' % (i + 1, ids[i], id))
            sequences[i].append(sequence.strip())
            i += 1
        return cls(sequences, ids)

    @classmethod
    def format_clustal_msa(cls, ids, sequences):
        out = ['CLUSTAL like multiple sequence alignment\n\n']
        ids = [id[:30] for id in ids]
        if len(set(ids)) != len(ids):
            raise ValueError('first 30 characters of each id must be unique') 
        id_width = max(len(id) for id in ids)
        block_length = ((80 - id_width) / 10) * 10
        for i in range(0, len(sequences[0]), block_length):
            for id, sequence in zip(ids, sequences):
                out.append("%-*s %s" % (id_width + 5, id, sequence[i:i+block_length].upper().replace('.', '-')))
            out.append('\n') # Not bothering with conservation punctuation 
        return '\n'.join(out)

    def to_str(self):
        return self.format_clustal_msa(self.ids, self.sequences)

class ReadClustalMSA(Action):
    action_name = 'open-clustal-alignment'
    path = ['Open', 'Clustal format alignment']
    tooltip = 'Read a Clustal format alignment file.'

    @classmethod
    def applicable(cls, target=None, coord=None):
        if target.msaview_classname == 'data.msa':
            return cls(target)

    def get_options(self):
        return [Option(propname='location', default='', value='', nick='Location', tooltip='The alignment file to read.')]

    def run(self):
        msa = ClustalFormatMSA.from_text(open(self.params['location']))
        self.target.set_msa(msa.sequences, self.params['location'], msa.ids)
    
register_action(ReadClustalMSA)

class SaveClustalMSA(Action):
    action_name = 'save-clustal-alignment'
    path = ['Save', 'Clustal like alignment']
    tooltip = 'Save the alignment in Clustal like format (without conservation punctuation).'

    @classmethod
    def applicable(cls, target=None, coord=None):
        if target.msaview_classname == 'data.msa':
            return cls(target)

    def get_options(self):
        try:
            path = os.path.splitext(self.target.path)[0] + '.aln'
        except:
            path = ''
        return [Option(propname='location', default=path, value=path, nick='Location', tooltip='Where to save the alignment.')]

    def run(self):
        alignment = open(self.params['location'], 'w')
        alignment.write(ClustalFormatMSA.format_clustal_msa(self.target.ids, self.target.sequences))
        self.target.path = self.params['location']
    
register_action(SaveClustalMSA)

class SaveCopyClustalMSA(Action):
    action_name = 'save-copy-clustal-alignment'
    path = ['Save', 'Clustal like alignment (copy)']
    tooltip = 'Save a copy of the alignment in Clustal like format (without conservation punctuation).'

    @classmethod
    def applicable(cls, target=None, coord=None):
        if target.msaview_classname == 'data.msa':
            return cls(target)

    def get_options(self):
        try:
            path = os.path.splitext(self.target.path)[0] + '.aln'
        except:
            path = ''
        return [Option(propname='location', default=path, value=path, nick='Location', tooltip='Where to save the alignment.')]

    def run(self):
        alignment = open(self.params['location'], 'w')
        alignment.write(ClustalFormatMSA.format_clustal_msa(self.target.ids, self.target.sequences))
    
register_action(SaveCopyClustalMSA)
