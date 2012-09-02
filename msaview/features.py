import itertools

import gobject

from action import (Action,
                    register_action)
from component import (Change, 
                       Component, 
                       prop)
from preset import (ComponentSetting,
                    presets)
from options import Option
from selection import Region
from sequence_information import get_id_index

class ContiguousRegion(object):
    def __init__(self, parts=None):
        if parts is None:
            parts = []
        self.parts = parts
        
    start = property(lambda self: self.parts[0].start)
    length = property(lambda self: len(self))
    
    def __len__(self):
        if not self.parts:
            return 0 
        return self.parts[-1].start + self.parts[-1].length - self.parts[0].start
    
    def __eq__(self, other):
        return isinstance(other, self.__class__) and other.parts == self.parts
    
    def __hash__(self):
        return hash((self.__class__, tuple(self.parts)))

    def __contains__(self, i):
        return self.start <= i < self.start + self.length

    def __repr__(self):
        return "<%s start:%s length:%s>" % (object.__repr__(self).split()[0][1:], self.start, self.length)
    
    def copy(self):
        parts = [p.copy() for p in self.parts]
        return self.__class__(parts)
    
def make_regions(position_features, test=None):
    if isinstance(test, str):
        value = test
        test = lambda x: x == value
    regions = []
    previous = None
    for i, feature in enumerate(position_features):
        if test(feature):
            if previous == i - 1:
                regions[-1].length += 1
            else:
                regions.append(Region(i, length=1))
            previous = i
    return regions

def map_regions(regions, msa_positions, offset=0):
    mapped_regions = []
    for region in regions:
        i = max(0, region.start - offset)        
        if i >= len(msa_positions):
            break
        last = region.start - offset + region.length - 1
        previous = None
        mapped = ContiguousRegion()
        while i <= min(last, len(msa_positions) - 1):
            msapos = int(msa_positions[i])
            if previous == msapos - 1:
                mapped[-1].length += 1
            else:
                mapped.append(Region(msapos, length=1))
            previous = msapos
            i += 1
        if mapped:
            mapped_regions.append(mapped)
    return mapped_regions

def map_region_to_msa(region, msa_positions, offset=0):
    i = max(0, region.start - offset)        
    if i >= len(msa_positions):
        return
    last = region.start - offset + region.length - 1
    previous = None
    mapped = ContiguousRegion()
    while i <= min(last, len(msa_positions) - 1):
        msapos = int(msa_positions[i])
        if previous == msapos - 1:
            mapped.parts[-1].length += 1
        else:
            mapped.parts.append(Region(msapos, length=1))
        previous = msapos
        i += 1
    return mapped or None

class SequenceFeature(object):
    def __init__(self, sequence_index=None, sequence_id=None, source=None, name=None, region=None, mapping=None, description=None):
        self.sequence_index = sequence_index
        self.sequence_id = sequence_id
        self.source = source
        self.name = name
        self.region = region
        self.mapping = mapping
        self.description = description

    def __eq__(self, other):
        try:
            return (isinstance(other, self.__class__) and
                    other.sequence_index == self.sequence_index and
                    other.sequence_id == self.sequence_id and
                    other.source == self.source and
                    other.name == self.name and
                    other.region == self.region and
                    other.mapping == self.mapping and
                    other.description == self.description)
        except AttributeError:
            return False
        
    def __hash__(self):
        return hash((self.sequence_index, self.sequence_id, self.source, self.name, self.region, self.mapping, self.description))
    
    def copy(self):
        return self.__class__(self.sequence_index, self.sequence_id, self.source, self.name, self.region.copy(), self.mapping.copy(), self.description)

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
    
    def equal(self, other):
        if isinstance(other, self.__class__):
            return self.is_similarly_annotated(other)
        return self.is_similarly_annotated(other) and other.is_similarly_annotated(self)
    
    def map_to_msa(self, msa, offset=0):
        self.mapping = map_region_to_msa(self.region, msa.msa_positions[self.sequence_index], offset)
        
    def get_details(self):
        return None
    
    def to_str(self):
        msg = "%s %s-%s" % (self.name, self.region.start, self.region.start + self.region.length)
        if self.description:
            return msg + " " + self.description
        return msg

    def to_markup(self, color=presets.get_value('color:black')):
        """Return markup appropriate for a tooltip.
        
        color can optionally be applied to a pertinent segment of the returned markup.
        
        """
        template = "<span foreground=%r weight='bold'>%s</span> %s-%s"
        markup = template % (color.to_str(), self.name.replace('<', '&lt;'), self.region.start, self.region.start + self.region.length)
        if self.description:
            markup += " (%s)" % self.description
        return markup

class GFFFeature(SequenceFeature):
    def __init__(self, sequence_index=None, sequence_id=None, source=None, name=None, region=None, mapping=None, description=None, score=None, strand=None, frame=None, attributes=None):
        self.sequence_index = sequence_index
        self.sequence_id = sequence_id
        self.source = source
        self.name = name
        self.region = region
        self.mapping = mapping
        self.description = description
        self.score = score
        self.strand = strand
        self.frame = frame
        if isinstance(attributes, str):
            attributes = (attributes,)
        self.attributes = attributes
        if attributes:
            self._attributes = frozenset(s.lower() for s in attributes)
        else: 
            self._attributes = frozenset([])

    def __hash__(self):
        return hash((self.sequence_index, self.sequence_id, self.source, self.name, self.region, self.mapping, self.description, self.score, self.strand, self.frame, self._attributes))
    
    def __eq__(self, other):
        return (isinstance(other, self.__class__) and
                other.sequence_index == self.sequence_index and
                other.sequence_id == self.sequence_id and
                other.source == self.source and
                other.name == self.name and
                other.region == self.region and
                other._attributes == self._attributes and
                other.mapping == self.mapping and
                other.strand == self.strand and
                other.frame == self.frame)

    def copy(self):
        return self.__class__(self.sequence_index, self.sequence_id, self.source, self.name, self.region.copy(), self.mapping.copy(), self.description, self.score, self.strand, self.frame, tuple(self.attributes) if self.attributes else None)
        
    @classmethod
    def from_gff_line(cls, line):
        """This is what we're parsing:
        seqname  source    feature  start    end   score strd  frm  [attribute [ ; ... ] ]
        SEQ1    netgene    splice5    172    173    0.94    +    .  apa 2 hus ; bil 
        """
        words = line.split('\t')
        attributes = ()
        description = None
        if len(words) > 8 and words[8] != '.':
            attributes = tuple(s.strip().replace('%3B', ';') for s in words[8].split(';'))
            description = words[8]
        start=int(words[3]) - 1 
        stop=int(words[4])
        region = Region(start, stop - start) 
        return cls(sequence_id=words[0],
                   source=words[1],
                   name=words[2],
                   region=region,
                   description=description,
                   score=float(words[5]) if words[5] != '.' else None,
                   strand=words[6] if words[6] != '.' else None,
                   frame=words[7] if words[7] != '.' else None,
                   attributes=attributes)
    
class SequenceFeatureRegistry(Component):
    __gproperties__ = dict(
        msa = (
            gobject.TYPE_PYOBJECT,
            'msa',
            'the multiple sequence alignment containing the sequences',
            gobject.PARAM_READWRITE))
    
    def __init__(self, msa=None):
        Component.__init__(self)
        self.features = []
        self.msa = msa
        
    msaview_classname = 'data.sequence_features'

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
        
    def find(self, test, sequence_index=None):
        if isinstance(test, str):
            category = test
            test = lambda e: e.category == category
        if sequence_index is None:
            it = itertools.chain(*self.features)
        else:
            it = self.features[sequence_index]
        for entry in it:
            if test(entry):
                return entry
             
    def findall(self, test, sequence_index=None):
        if isinstance(test, str):
            category = test
            test = lambda e: e.category == category
        features = []
        if sequence_index is None:
            it = itertools.chain(*self.features)
        else:
            it = self.features[sequence_index]
        for entry in it:
            if test(entry):
                features.append(entry)
        return features
        
    def remove_features(self, features):
        if isinstance(features, SequenceFeature):
            features = [features]
        for entry in features:
            self.features[entry.sequence_index].remove(entry)
        self.emit('changed', Change('features', 'removed', features))
   
    def clear(self):
        l = []
        if self.msa:
            l = self.msa.sequences
        self.features = [list() for x in l]
        self.emit('changed', Change('features'))
        
    def integrate(self, ancestor, name=None):
        msa = ancestor.find_descendant('data.msa')
        if msa is None:
            msa = ancestor.integrate_descendant('data.msa')
            if msa is None:
                raise TypeError('no suitable parent')
        self.msaview_name = msa.add(self, name)
        self.msa = msa
        return self.msaview_name

    def add_features(self, features):
        if isinstance(features, SequenceFeature):
            features = [features]
        new_features = []
        for feature in features:
            feature_list = self.features[feature.sequence_index]
            for i, f in enumerate(feature_list):
                if feature == f:
                    break
                if feature.mapping.start < f.mapping.start:
                    feature_list.insert(i, feature)
                    break
            else:
                feature_list.append(feature)
                new_features.append(feature)
        if new_features:
            self.emit('changed', Change('features', 'added', new_features))
   
class SequenceFeatureRegistrySetting(ComponentSetting):
    component_class = SequenceFeatureRegistry

presets.register_component_defaults(SequenceFeatureRegistrySetting)
        
# Actions:

def iter_gff_annotations(gff_file, filter=None):
    for line in gff_file:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        yield GFFFeature.from_gff_line(line)

class ImportGFFAnnotations(Action):
    action_name = 'import-gff-annotations'
    path = ['Import', 'Sequence features', 'gff annotations']
    tooltip = 'Import feature annotations from a general feature format file.'
    
    @classmethod
    def applicable(cls, target, coord=None):
        if target.msaview_classname == 'data.msa':
            return cls(target.features)
        if target.msaview_classname == 'data.sequence_features':
            return cls(target)
    
    def run(self):
        gff = open(self.params['location'])
        features = []
        for annotation in iter_gff_annotations(gff):
            annotation.sequence_index = get_id_index(self.target.msa.ids, annotation.sequence_id)
            if annotation.sequence_index is None:
                continue
            annotation.mapping = map_region_to_msa(annotation.region, self.target.msa.msa_positions[annotation.sequence_index])
            if annotation.mapping is None:
                continue
            features.append(annotation)
        self.target.add_features(features)

    def get_options(self):
        path = ''
        if self.target and self.target.msa.path:
            path = self.target.msa.path + '.gff'
        return [Option(propname='location', default=path, value=path, nick='Location', tooltip='Where to read the GFF annotations from.')]

register_action(ImportGFFAnnotations)
