"""MSAView - Disopred support.

Copyright (c) 2011 Joel Hedlund.

Contact: Joel Hedlund <yohell@ifm.liu.se>

MSAView is a modular, configurable and extensible package for analysing and 
visualising multiple sequence alignments and sequence features. 

This package provides support for parsing dispored result files (must be 
named according to sequence id, e.g: O43736.disopred).
 
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

from msaview import action
from msaview.options import Option
from msaview.features import (SequenceFeature,
                              make_regions, 
                              map_region_to_msa)

class DisopredPrediction(object):
    def __init__(self, sequence_id=None, sequence=None, regions=None):
        self.sequence_id = sequence_id
        self.sequence = sequence
        if regions is None:
            regions = []
        self.regions = regions
        
    @classmethod
    def from_file(cls, f, sequence_id=None):
        if sequence_id is None:
            sequence_id = os.path.splitext(os.path.basename(f.name))[0]
        sequence = []
        prediction = []
        for line in f:
            words = line.split()
            if len(words) != 2:
                continue
            linetype = words[0].lower()
            if linetype == 'aa:':
                sequence.append(words[1])
            elif linetype == 'pred:':
                prediction.append(words[1])
        regions = make_regions(''.join(prediction), '*')
        return cls(sequence_id, sequence=''.join(sequence), regions=regions)
        
class ImportDisopredRegions(action.Action):
    action_name = 'import-disopred-predictions'
    path = ['Import', 'Sequence features', 'Disopred predictions for sequence']
    tooltip = 'Import predictions of natively disordered regions from a disopred result file.'

    @classmethod
    def applicable(cls, target, coord=None):
        if target.msaview_classname != 'data.msa':
            return
        if not coord or not coord.sequence:
            return
        return cls(target, coord)
        
    def get_options(self):
        location = ''
        if self.target:
            if self.target.path:
                location = os.path.dirname(self.target.path)
            location = os.path.join(location, self.target.ids[self.coord.sequence] + '.disopred')
        return [Option(None, 'location', location, location, 'Location', 'Disopred prediction file to load.')]
    
    def run(self):
        f = open(self.params['location'])
        prediction = DisopredPrediction.from_file(f)
        f.close()
        if not prediction:
            return
        sequence_index = self.coord.sequence
        offset = prediction.sequence.find(self.target.unaligned[sequence_index])
        if offset < 0:
            return
        msa_positions = self.target.msa_positions[sequence_index]
        sequence_id = self.target.ids[sequence_index]
        features = []
        for region in prediction.regions:
            mapping = map_region_to_msa(region, msa_positions, offset)
            if not mapping:
                continue
            features.append(SequenceFeature(sequence_index, sequence_id, 'disopred', 'natively disordered', region, mapping))
        self.target.features.add_features(features)

action.register_action(ImportDisopredRegions)
