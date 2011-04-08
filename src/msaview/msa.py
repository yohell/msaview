from itertools import chain
import os
import re 
import sys

import gobject
import numpy

from action import (Action,
                    CopyText,
                    ExportText,
                    register_action)
from component import (Change, 
                       Component, 
                       prop)
import log
from preset import (ComponentSetting,
                    presets)
from options import (BooleanOption,
                     FloatOption,
                     Option)
from selection import (Area, 
                       Selection, 
                       Region,
                       RegionSelection)

module_logger = log.get_module_logger(__file__)

class Sequence(object):
    def __init__(self, id, sequence, description=None):
        self.id = id
        self.sequence = sequence
        self.description = description

    @classmethod
    def format_fasta(cls, id, sequence, description=None, sequence_line_length=60):
        out = ['>%s%s' % (id, ' ' + description if description else '')]
        for i in range(0, len(sequence), sequence_line_length):
            out.append(sequence[i:i + sequence_line_length])
        return '\n'.join(out)          
    
    def to_fasta(self, sequence_line_length=60):
        return self.format_fasta(self.id, self.sequence, self.description, sequence_line_length)          

class ParseError(Exception):
    def __init__(self, value=None, reason=None, msg=None):
        self.value = value
        self.reason = reason
        self.msg = msg
        
    def __str__(self):
        return self.msg or "bad value %r: %s" % (self.value, self.reason)

def parse_sequence_boundary(boundary_def, sequence_regex=False):
    try:
        i = int(boundary_def)
        if not i:
            raise ValueError
        if i > 0:
            i -= 1
            return i
        return i
    except ValueError:
        pass
    if sequence_regex:
        try:
            return re.compile(boundary_def, re.IGNORECASE)
        except:
            raise ParseError(boundary_def, 'not a valid regular expression')
    return boundary_def

def parse_position_boundary(boundary_def):
    try:
        i = int(boundary_def)
        if not i:
            raise ValueError
        if i > 0:
            i -= 1
            return i
    except ValueError:
        pass
    try:
        return re.compile(boundary_def, re.IGNORECASE)
    except:
        raise ParseError(boundary_def, 'not a valid regular expression')

def parse_position_region_literal(region_def, sequence_regex=False):
    words = region_def.split()
    if len(words) > 2:
        raise ParseError(region_def, "max one space allowed")
    sequence = None
    if len(words) == 2:
        sequence = parse_sequence_boundary(words[0], sequence_regex)
    boundaries = words[-1].split(':')
    if len(boundaries) > 2:
        raise ParseError(region_def, "max one ':' allowed in boundary defs")
    positions = [parse_position_boundary(s) for s in boundaries]
    return (sequence, positions)

def parse_sequence_region_literal(region_def, sequence_regex=False):
    words = region_def.split()
    if len(words) > 2:
        raise ParseError(region_def, "max one space allowed")
    return [parse_sequence_boundary(s, sequence_regex) for s in words]

class MSA(Component):
    __gproperties__ = dict(
        array = (gobject.TYPE_PYOBJECT,
            'array',
            'the letters in the msa as a numpy array',
            gobject.PARAM_READABLE),
        column_array = (gobject.TYPE_PYOBJECT,
            'column array',
            'a numpy byte array interface to the letters in the msa, column oriented',
            gobject.PARAM_READWRITE),
        descriptions = (gobject.TYPE_PYOBJECT,
            'descriptions',
            'the sequence descriptions',
            gobject.PARAM_READWRITE),
        ids = (gobject.TYPE_PYOBJECT,
            'ids',
            'the sequence identifiers',
            gobject.PARAM_READWRITE),
        msa_positions = (gobject.TYPE_PYOBJECT,
            'msa positions',
            'msa positions for each residue in each sequence',
            gobject.PARAM_READWRITE),
        path = (gobject.TYPE_PYOBJECT,
            'path',
            'the path to the msa file',
            gobject.PARAM_READWRITE),
        sequences = (gobject.TYPE_PYOBJECT,
            'sequences',
            'the letters in the alignment as a tuple of strings',
            gobject.PARAM_READWRITE),
        selection = (gobject.TYPE_PYOBJECT,
            'selection',
            'information about the individual sequences in the alignment',
            gobject.PARAM_READWRITE),
        sequence_array = (gobject.TYPE_PYOBJECT,
            'sequence array',
            'a numpy byte array interface to the letters in the msa, sequence oriented',
            gobject.PARAM_READWRITE),
        sequence_information = (gobject.TYPE_PYOBJECT,
            'sequence annotations',
            'information about the individual sequences in the alignment',
            gobject.PARAM_READWRITE),
        unaligned = (gobject.TYPE_PYOBJECT,
            'unaligned',
            'the unaligned sequences as a tuple of strings',
            gobject.PARAM_READWRITE),
        ungapped = (gobject.TYPE_PYOBJECT,
            'ungapped',
            'which letters are non-gaps as a numpy boolean array, shape (sequences, position)',
            gobject.PARAM_READABLE)
        )
    
    msaview_classname = 'data.msa'
    logger = log.get_logger(msaview_classname)
    gapchars = '.-'
    
    def __init__(self):
        Component.__init__(self)
        self.features = self.integrate_descendant('data.sequence_features')
        self.sequence_information = self.integrate_descendant('data.sequence_information')
        self.selection = Selection(self)
    
    column_array = prop('column_array', readonly=True)
    descriptions = prop('descriptions')
    ids = prop('ids')
    msa_positions = prop('msa_positions')
    path = prop('path')
    sequences = prop('sequences')
    selection = prop('selection')
    sequence_array = prop('sequence_array', readonly=True)
    sequence_information = prop('sequence_information')
    unaligned = prop('unaligned', readonly=True)
    ungapped = prop('ungapped', readonly=True)
    
    def do_set_property(self, pspec, value):
        name = pspec.name.replace('-', '_')
        if name in ['descriptions', 'ids', 'path']:
            if value != getattr(self, name):
                self.propvalues[name] = value
                self.emit('changed', Change(name))
            return
        Component.do_set_property(self, pspec, value) 
    
    def __len__(self):
        if self.sequences:
            return self.ungapped.shape[1]
        return 0

    def __hash__(self):
        return hash((MSA, self.sequences))
           
    def __eq__(self, other):
        return isinstance(other, self.__class__) and other.sequences == self.sequences

    @log.trace
    def _parse_sequences(self, sequences):
        import time
        t0 = time.time()
        if sequences is not None:
            if not isinstance(sequences, tuple):
                sequences = tuple(sequences)
            for s in sequences:
                if not isinstance(s, basestring):
                    raise TypeError("sequences must be a sequence of basestrings")
        if sequences == self.sequences: 
            return None
        n_sequences = len(sequences)
        n_positions = max(len(s) for s in sequences)
        msa_size = (n_sequences, n_positions) 
        sequence_array = numpy.empty(msa_size, dtype=numpy.uint8)
        sequence_array.shape = msa_size
        sequence_array[:] = ord(' ')
        unaligned = []
        self.logger.debug('building arrays new style, %.3fs' % (time.time() - t0))
        for i, sequence in enumerate(sequences):
            start = i * n_positions
            length = len(sequence)
            sequence_array.data[start:start + length] = sequence
            for gapchar in self.gapchars + ' ':
                sequence = sequence.replace(gapchar, '')
            unaligned.append(sequence)
        gapchars = numpy.ones(256, bool)
        gapchars[[ord(s) for s in self.gapchars + ' ']] = False
        ungapped = gapchars[sequence_array]
        msa_positions = []
        for i in range(n_sequences):
            msa_positions.append(ungapped[i].nonzero()[0])
        sequence_array.flags.writeable = False
        column_array = numpy.frombuffer(sequence_array.T.tostring(), dtype=numpy.uint8)
        column_array.shape = (msa_size[1], msa_size[0])
        self.logger.debug('finished building arrays new style, %.3fs' % (time.time() - t0))
        return column_array, msa_positions, sequences, sequence_array, ungapped, unaligned
    
    def do_set_property_sequences(self, pspec, sequences):
        x = self._parse_sequences(sequences)
        if x is None:
            return
        column_array, msa_positions, sequences, sequence_array, ungapped, unaligned = x
        self.propvalues.update(column_array=column_array, 
                               msa_positions=msa_positions, 
                               sequences=sequences, 
                               sequence_array=sequence_array, 
                               ungapped=ungapped, 
                               unaligned=unaligned)
        self.emit('changed', Change('sequences'))

    def set_msa(self, sequences, path=None, ids=None, descriptions=None):
        x = self._parse_sequences(sequences)
        if x is None or (sequences == self.sequences and descriptions == self.descriptions and ids == self.ids and path == self.path): 
            return
        column_array, msa_positions, sequences, sequence_array, ungapped, unaligned = x
        self.propvalues.update(column_array=column_array, 
                               descriptions=descriptions, 
                               ids=ids, 
                               msa_positions=msa_positions,
                               path=path, 
                               sequences=sequences, 
                               sequence_array=sequence_array, 
                               ungapped=ungapped, 
                               unaligned=unaligned)
        self.emit('changed', Change())

    @log.trace
    def read_fasta(self, file):
        path = file.name
        ids = []
        descriptions = []
        sequence_parts = []
        for line in file:
            if line.lstrip().startswith('>'):
                words = line.split(None, 1)
                ids.append(words[0][1:])
                description = None
                if len(words) == 2:
                    description = words[1].rstrip()
                descriptions.append(description)
                sequence_parts.append([])
            else:
                sequence_parts[-1].append(line.strip())
        sequences = [''.join(part) for part in sequence_parts]
        self.set_msa(sequences, path, ids, descriptions)

    def write_fasta(self, file):
        for i in range(len(self.sequences)):
            print >> file, Sequence.format_fasta(self.ids[i], self.sequences[i], self.descriptions[i])
        if file.name:
            self.path = file.name

    def sequence_position(self, sequence_index, msa_position):
        return sum(self.ungapped[sequence_index, :msa_position])

    def get_sequence_index(self, test, regex=False, min=0):
        """Return the matching sequence index. 
        
        test can be an index (int, possibly negative) an exact id (str) or a regex (will be .searched).
        min (int, possibly negative) gives the start of the search. If regex is True
        then test will be converted to a case insensitive regex if it is a str.
        
        """
        if min < 0:
            min = len(self.sequences) + min
            if not (0 <= min < len(self.sequences)):
                raise IndexError('min out of range')
        if isinstance(test, int):
            index = test
            if test < 0:
                index = len(self.sequences) - test
                if index < 0:
                    raise IndexError('index out of range')
            if index < min:
                raise ValueError('index must be greater than min')
            return index
        else:
            if regex and isinstance(test, str):
                test = re.compile(test, re.IGNORECASE)
            if isinstance(test, str):
                match = lambda s: s == test
            else:
                match = lambda s: test.search(s)
            for i in range(min, len(self.sequences)):
                if match(self.ids[i]):
                    return i
            else:
                raise ValueError('no such id')

    def get_selected_sequences(self):
        sequences = []
        if self.selection.positions or self.selection.sequences:
            if self.selection.positions:
                pos_regions = self.selection.positions.regions
            else:
                pos_regions = [Region(0, len(self))]
            if self.selection.sequences:
                seq_regions = self.selection.sequences.regions
            else:
                seq_regions = [Region(0, len(self.sequences))]
            for seq_region in seq_regions:
                for seq in range(seq_region.start, seq_region.start + seq_region.length):
                    id = self.ids[seq]
                    description = self.descriptions[seq] if self.descriptions else None
                    regions = []
                    for pos_region in pos_regions:
                        regions.append(self.sequences[seq][pos_region.start:pos_region.start + pos_region.length])
                    sequences.append(Sequence(id, ''.join(regions), description))
        else:
            for i, area in enumerate(self.selection.areas.areas):
                for seq in range(area.sequences.start, area.sequences.start + area.sequences.length):
                    id = "[area%s]" % str(i+1) + self.ids[seq] 
                    description = self.descriptions[seq] if self.descriptions else None
                    sequence = self.sequences[seq][area.positions.start:area.positions.start + area.positions.length]
                    sequences.append(Sequence(id, sequence, description))
        return sequences

    def find_motif_in_sequence(self, motif, sequence_index, min=0):
        if isinstance(motif, str):
            motif = re.compile(motif, re.IGNORECASE)
        return motif.search(self.unaligned[sequence_index], self.sequence_position(sequence_index, min))
    
    def find_motif_in_msa(self, motif, min=0):
        if isinstance(motif, str):
            motif = re.compile(motif, re.IGNORECASE)
        start = len(self)
        match = None
        sequence_index = None
        for i in range(len(self.sequences)):
            m = self.find_motif_in_sequence(motif, i, min)
            if m and m.start() < start:
                sequence_index = i
                match = m
                start = self.msa_positions[i][m.start()]
                if start == min:
                    break
        return sequence_index, match
    
    def get_position_region_for_sequence(self, sequence_index, start, end=None, min=0):
        """Get a Region() for positions in a given reference sequence.
        
        start and end can be sequence positions or regexes or (case insensitive 
        regex literals). If end is a regex, it will be used to search for a 
        (possibly overlapping) match after start. If end is none, then the 
        extents of the start motif will be used. 
         
        """
        first_position = None
        if isinstance(start, str):
            start = re.compile(start, re.IGNORECASE)
        if isinstance(end, str):
            end = re.compile(end, re.IGNORECASE)
        if isinstance(start, int):
            first_position = self.msa_positions[sequence_index][start]
            last_position = first_position
            if first_position < min:
                raise ValueError('start index must be higher than min')
        else:
            match = self.find_motif_in_sequence(start, sequence_index, min)
            if not match:
                raise ValueError('start motif not found')
            first_position = self.msa_positions[sequence_index][match.start()]
            last_position = self.msa_positions[sequence_index][match.end() - 1]
        if isinstance(end, int):
            last_position = self.msa_positions[sequence_index][end]
        elif end is not None:
            match = self.find_motif_in_sequence(end, sequence_index, first_position)
            if not match:
                raise ValueError('end motif not found')
            last_position = self.msa_positions[sequence_index][match.end() - 1]
        length = last_position - first_position + 1
        if length <= 0:
            raise ValueError('start must precede end')
        return Region(first_position, length)
    
    def get_position_region_for_msa(self, start, end=None, min=0):
        """Get a Region() for positions in the MSA.
        
        start and end can be msa positions or regexes or (case insensitive 
        regex literals). If end is a regex, it will be used to search for a 
        (possibly overlapping) match after start. If end is none, then the 
        extents of the start motif will be used. 
         
        """
        first_position = None
        if isinstance(start, str):
            start = re.compile(start, re.IGNORECASE)
        if isinstance(end, str):
            end = re.compile(end, re.IGNORECASE)
        if isinstance(start, int):
            first_position = start
            last_position = start
            if first_position < min:
                raise ValueError('start index must be higher than min')
        else:
            sequence_index, match = self.find_motif_in_msa(start, min)
            if not match:
                raise ValueError('start motif not found')
            first_position = self.msa_positions[sequence_index][match.start()]
            last_position = self.msa_positions[sequence_index][match.end() - 1]
        if isinstance(end, int):
            last_position = end
        elif end is not None:
            sequence_index, match = self.find_motif_in_msa(end, first_position)
            if not match:
                raise ValueError('end motif not found')
            last_position = self.msa_positions[sequence_index][match.end() - 1]
        length = last_position - first_position + 1
        if length <= 0:
            raise ValueError('start must precede end')
        return Region(first_position, length)
    
    def get_position_region(self, start, end=None, sequence_index=None, min=0):
        """Get a position Region(). Convenience method."""
        if sequence_index is not None:
            return self.get_position_region_for_sequence(sequence_index, start, end, min)
        return self.get_position_region_for_msa(start, end, min)

    def get_position_regions(self, start, end=None, sequence_index=None):
        """Get multiple matching Region()s. 

        Returns [] if no matching regions are found.
        """
        regions = []
        min = 0
        while min < len(self):
            try:
                region = self.get_position_region(start, end, sequence_index, min)
            except (IndexError, ValueError), e:
                break
            regions.append(region)
            min = region.start + region.length
        return regions             
    
    def get_sequence_region(self, start, end=None, regex=False, min=0):
        length = 1
        first_sequence = self.get_sequence_index(start, regex, min)
        if end is not None:
            last_sequence = self.get_sequence_index(end, regex, first_sequence + 1)
            length = last_sequence - first_sequence + 1
        return Region(first_sequence, length)
             
    def get_sequence_regions(self, start, end=None, regex=False):
        regions = []
        min = 0
        while min < len(self.sequences):
            try:
                region = self.get_sequence_region(start, end, regex, min)
            except (IndexError, ValueError), e:
                break
            regions.append(region)
            min = region.start + region.length
        return regions             

    def get_area(self, pos_start=None, pos_end=None, seq_start=None, seq_end=None, reference_index=None, id_regex=False):
        pos = self.get_position_region(pos_start, pos_end, reference_index)
        seq = self.get_sequence_region(seq_start, seq_end, id_regex)
        return Area(pos, seq)
    
    def get_areas(self, pos_start, pos_end=None, seq_start=None, seq_end=None, pos_multiple=False, seq_multiple=False, reference_index=None, id_regex=False):
        if seq_start is None and seq_end is None:
            sequence_regions = [Region(0, len(self.sequences))]
        elif seq_multiple:
            sequence_regions = self.get_sequence_regions(seq_start, seq_end, id_regex)
        else:
            sequence_regions = [self.get_sequence_region(seq_start, seq_end, id_regex)]
        areas = []
        if reference_index is not None or (isinstance(pos_start, int) and (pos_end is None or isinstance(pos_end, int))):
            if pos_multiple:
                position_regions = self.get_position_regions(pos_start, pos_end, reference_index) 
            else:
                position_regions = [self.get_position_region(pos_start, pos_end, reference_index)]
            for sequence_region in sequence_regions:
                for position_region in position_regions:
                    areas.append(Area(position_region.copy(), sequence_region.copy()))
            return areas
        for sequence_region in sequence_regions:
            for sequence_index in range(sequence_region.start, sequence_region.start + sequence_region.length):
                if pos_multiple:
                    for pos_region in self.get_position_regions(pos_start, pos_end, sequence_index):
                        areas.append(Area(pos_region, Region(sequence_index, 1)))
                else:
                    pos_region = self.get_position_region(pos_start, pos_end, sequence_index)
                    areas.append(Area(pos_region, Region(sequence_index, 1)))
        return areas
    
    def integrate(self, ancestor, name=None):
        self.msaview_name = ancestor.add(self, name)
        m = ancestor.find_ancestor('root')
        m.descendants.register(self.features, self.features.msaview_name)
        m.descendants.register(self.sequence_information, self.sequence_information.msaview_name)
        return self.msaview_name 

    
class MSASetting(ComponentSetting):
    component_class = MSA
    
presets.register_component_defaults(MSASetting)

# Actions

class ReadFasta(Action):
    action_name = 'open-fasta-alignment'
    path = ['Open', 'Fasta alignment']
    tooltip = 'Read a gapped fasta alignment file.'

    @classmethod
    def applicable(cls, target=None, coord=None):
        if target.msaview_classname == 'data.msa':
            return cls(target)

    def get_options(self):
        return [Option(propname='location', default='', value='', nick='Location', tooltip='The alignment file to read.')]

    def run(self):
        self.target.read_fasta(open(self.params['location']))
    
register_action(ReadFasta)

class SaveFasta(Action):
    action_name = 'save-fasta-alignment'
    path = ['Save', 'Fasta alignment']
    tooltip = 'Save alignment in gapped fasta format.'

    @classmethod
    def applicable(cls, target=None, coord=None):
        if target.msaview_classname == 'data.msa':
            return cls(target)

    def get_options(self):
        try:
            path = os.path.splitext(self.target.path)[0] + '.gfasta'
        except:
            path = ''
        return [Option(propname='location', default='', value='', nick='Location', tooltip='Where to save the alignment.')]

    def run(self):
        self.target.write_fasta(open(self.params['location'], 'w'))
    
register_action(SaveFasta)

class SaveFastaCopy(Action):
    action_name = 'save-copy-fasta-alignment'
    path = ['Save', 'Fasta alignment (copy)']
    tooltip = 'Save a copy of the alignment in gapped fasta format.'

    @classmethod
    def applicable(cls, target=None, coord=None):
        if target.msaview_classname == 'data.msa':
            return cls(target)

    def get_options(self):
        try:
            path = os.path.splitext(self.target.path)[0] + '.gfasta'
        except:
            path = ''
        return [Option(propname='location', default='', value='', nick='Location', tooltip='Where to save the alignment.')]

    def run(self):
        old_path = self.target.path 
        self.target.write_fasta(open(self.params['location'], 'w'))
        self.target.path = old_path
    
register_action(SaveFastaCopy)

class SelectionAction(Action):
    @classmethod
    def applicable(cls, target=None, coord=None):
        if target.msaview_classname == 'data.msa' and target.selection:
            return cls(target)

class ClearSelection(SelectionAction):
    action_name = 'clear-selection'
    path = ['Select', 'Clear selection']
    tooltip = 'Select nothing.'
    
    def run(self):
        self.target.selection.clear()

register_action(ClearSelection)
        
class CopyRawSequences(CopyText, SelectionAction):
    action_name = 'copy-raw-sequences'
    path = ['Copy', 'Sequences', 'Sequences (raw)']
    tooltip = 'Copy raw sequences.'

    def get_text(self):
        return '\n'.join(o.sequence for o in self.target.get_selected_sequences())

class ExportRawSequences(ExportText, CopyRawSequences):
    action_name = 'export-raw-sequences'
    path = ['Export', 'Sequences', 'Sequences (raw)']
    tooltip = 'Export raw sequences.'

register_action(CopyRawSequences)
register_action(ExportRawSequences)
        
class CopyFastaSequences(CopyText, SelectionAction):
    action_name = 'copy-fasta-sequences'
    path = ['Copy', 'Sequences', 'Fasta']
    tooltip = 'Copy fasta sequences.'

    def get_text(self):
        return '\n'.join(o.to_fasta() for o in self.target.get_selected_sequences())

class ExportFastaSequences(ExportText, CopyFastaSequences):
    action_name = 'export-fasta-sequences'
    path = ['Export', 'Sequences', 'Fasta']
    tooltip = 'Export fasta sequences.'

register_action(CopyFastaSequences)
register_action(ExportFastaSequences)
        
class CopyUngappedFastaSequences(CopyText, SelectionAction):
    action_name = 'copy-ungapped-fasta-sequences'
    path = ['Copy', 'Sequences', 'Ungapped fasta']
    tooltip = 'Copy unaligned (ungapped) fasta sequences.'

    def get_text(self):
        sequences = self.target.get_selected_sequences()
        for o in sequences:
            o.sequence = o.sequence.replace('-', '').replace('.', '')
        return '\n'.join(o.to_fasta() for o in sequences)

class ExportUngappedFastaSequences(ExportText, CopyUngappedFastaSequences):
    action_name = 'export-ungapped-fasta-sequences'
    path = ['Export', 'Sequences', 'Ungapped fasta']
    tooltip = 'Export unaligned (ungapped) fasta sequences.'

register_action(CopyUngappedFastaSequences)
register_action(ExportUngappedFastaSequences)

class CopySequenceIDs(CopyText, SelectionAction):
    action_name = 'copy-sequence-ids'
    path = ['Copy', 'Sequence IDs']
    tooltip = 'Copy sequence identifiers.'

    def get_text(self):
        return '\n'.join(o.id for o in self.target.get_selected_sequences())
        
class ExportSequenceIDs(ExportText, CopySequenceIDs):
    action_name = 'export-sequence-ids'
    path = ['Export', 'Sequence IDs']
    tooltip = 'Export sequence identifiers.'

register_action(CopySequenceIDs)
register_action(ExportSequenceIDs)

class SequenceRangeOption(Option):
    def parse_str(self, string):
        return parse_sequence_region_literal(string, sequence_regex=True)

class BoundaryOption(Option):
    def parse_str(self, string):
        if not string:
            return
        try:
            return int(string.strip()) - 1
        except Exception, e:
            return string.strip()

    def to_str(self):
        if self.value is None:
            return ''
        return str(self.value)

class SelectSequences(Action):
    action_name = 'select-sequences'
    path = ['Select', 'Sequences']
    tooltip = 'Select sequences.'
    
    @classmethod
    def applicable(cls, target=None, coord=None):
        if target.msaview_classname == 'data.msa':
            return cls(target)
            
    def get_options(self):
        return [BoundaryOption(propname='start', value=None, default=None, nick='Start', tooltip='Index or ID for the first sequence in the range.'),
                BoundaryOption(propname='end', value=None, default=None, nick='End', tooltip='Index or ID for the last sequence in the range.'),
                BooleanOption(propname='regex', default=True, value=True, nick='Regex', tooltip='Use regular expressions to match sequence identifiers.'),
                BooleanOption(propname='find-all', default=True, value=True, nick='Find all', tooltip='Select all matching sequence ranges instead of only the first.')]
    
    def run(self):
        if self.params['find-all']:
            regions = self.target.get_sequence_regions(self.params['start'], self.params['end'], self.params['regex'])
        else:
            regions = [self.target.get_sequence_region(self.params['start'], self.params['end'], self.params['regex'])]
        self.target.selection.sequences.add(regions)
    
register_action(SelectSequences)

class SelectPositions(Action):
    action_name = 'select-positions'
    path = ['Select', 'Positions']
    tooltip = 'Select positions.'
    
    @classmethod
    def applicable(cls, target=None, coord=None):
        if target.msaview_classname == 'data.msa':
            return cls(target)
            
    def get_options(self):
        return [BoundaryOption(propname='start', value=None, default=None, nick='Start', tooltip='Index or motif start boundary in the range.'),
                BoundaryOption(propname='end', value=None, default=None, nick='End', tooltip='Index or motif for the end boundary in the range.'),
                BoundaryOption(propname='reference', value=None, default=None, nick='Reference sequence', tooltip='Sequence ID or index; treat indexes/motifs relative to this sequence instead of the MSA.'),
                BooleanOption(propname='regex', default=True, value=True, nick='Regex', tooltip='Use regular expressions to match the reference sequence identifier.'),
                BooleanOption(propname='find-all', default=True, value=True, nick='Find all', tooltip='Select all matching position ranges instead of only the first.')]

    def run(self):
        sequence_index = None
        reference = self.params['reference'] and self.params['reference'].strip()
        if reference:
            sequence_index = self.target.get_sequence_index(reference, self.params['regex'])
        if self.params['find-all']:
            regions = self.target.get_position_regions(self.params['start'], self.params['end'], sequence_index)
        else:
            regions = [self.target.get_position_region(self.params['start'], self.params['end'], sequence_index)]
        self.target.selection.positions.add(regions)
        
register_action(SelectPositions)

class SelectAreas(Action):
    action_name = 'select-areas'
    path = ['Select', 'Areas']
    tooltip = 'Select areas.'
    
    @classmethod
    def applicable(cls, target=None, coord=None):
        if target.msaview_classname == 'data.msa':
            return cls(target)
            
    def get_options(self):
        return [BoundaryOption(propname='positions-start', value=None, default=None, nick='Positions start', tooltip='Ungapped seqeunce index or motif for the beginning of the position range.'),
                BoundaryOption(propname='positions-end', value=None, default=None, nick='Positions end', tooltip='Ungapped index or motif for the end of the position range.'),
                BoundaryOption(propname='reference', value=None, default=None, nick='Reference sequence', tooltip='Sequence ID or index; treat indexes/motifs relative to this sequence instead of the MSA.'),
                BoundaryOption(propname='sequences-start', value=None, default=None, nick='Sequences start', tooltip='Index or motif for the beginning of the sequence range.'),
                BoundaryOption(propname='sequences-end', value=None, default=None, nick='Sequences end', tooltip='Index or motif for the end of the sequence range.'),
                BooleanOption(propname='regex', default=True, value=True, nick='Regex', tooltip='Use regular expressions to match sequence identifiers.'),
                BooleanOption(propname='find-all-positions', default=True, value=True, nick='Find all positions', tooltip='Select all matching position ranges instead of only the first.'),
                BooleanOption(propname='find-all-sequences', default=True, value=True, nick='Find all sequences', tooltip='Select all matching sequence ranges instead of only the first.')]

    def run(self):
        reference_index = None
        reference = self.params['reference'] and self.params['reference'].strip()
        if reference:
            reference_index = self.target.get_sequence_index(reference, self.params['regex'])
        areas = self.target.get_areas(self.params['positions-start'], 
                                      self.params['positions-end'], 
                                      self.params['sequences-start'], 
                                      self.params['sequences-end'], 
                                      self.params['find-all-positions'], 
                                      self.params['find-all-sequences'], 
                                      reference_index, 
                                      self.params['regex'])
        self.target.selection.areas.add(areas)
        
register_action(SelectAreas)

class SelectGappedPositions(Action):
    action_name = 'select-gapped-positions'
    path = ['Select', 'Gapped positions']
    tooltip = 'Select fully or partially gapped positions.'
    
    @classmethod
    def applicable(cls, target=None, coord=None):
        if target.msaview_classname != 'data.msa':
            return
        return cls(target)
    
    def get_options(self):
        return [FloatOption(None, 'tolerance', 0, sys.maxint, 0, 10, 0.01, 1, 2, 0, 0, 'Tolerance', 'Maximum number of non-gap characters in a column, < 1 means ratio.')]
    
    def run(self):
        if self.params['tolerance'] >= 1:
            min_gaps = len(self.target.sequences) - self.params['tolerance']
        else:
            min_gaps = int(round((1 - self.params['tolerance']) * len(self.target.sequences)))
        region = None
        gap_ords = [ord(s) for s in self.target.gapchars]
        for pos in range(len(self.target)):
            counts = numpy.bincount(self.target.column_array[pos])
            gaps = sum(counts[[i for i in gap_ords if i < len(counts)]], 0)
            if gaps < min_gaps:
                if region:
                    self.target.selection.positions.incorporate(region)
                    region = None
            elif region is None:
                region = Region(pos, 1)
            else:
                region.length += 1
        if region:
            self.target.selection.positions.incorporate(region)
        
register_action(SelectGappedPositions)
          
class DeletePositions(Action):
    action_name = 'delete-positions'
    path = ['Edit', 'Delete positions']
    tooltip = 'Delete selected positions.'
    
    @classmethod
    def applicable(cls, target=None, coord=None):
        if target.msaview_classname != 'data.msa':
            return
        if not (target.selection.positions or target.selection.areas):
            return
        return cls(target)
    
    def run(self):
        sel = RegionSelection()
        positions = iter(self.target.selection.positions.regions)
        areas = (a.positions for a in self.target.selection.areas.areas)
        for region in sorted(chain(positions, areas), key=lambda r: r.start):
            sel.incorporate(region)
        sel.invert(len(self.target))
        sequences = []
        for sequence in self.target.sequences:
            sequences.append(''.join(sequence[r.start:r.start+r.length] for r in sel.regions))
        self.target.selection.positions.clear()
        self.target.selection.areas.clear()
        path = self.target.path.strip('*') + '*'
        self.target.set_msa(sequences, path, self.target.ids, self.target.descriptions)
        
register_action(DeletePositions)
          
