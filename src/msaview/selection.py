import gobject

from component import (Change, 
                       Component, 
                       Connection, 
                       prop)

class Region(object):
    def __init__(self, start, length):
        self.start = start
        self.length = length
        
    def __contains__(self, value):
        return self.start <= value < self.start + self.length
    
    def __eq__(self, other):
        return isinstance(other, self.__class__) and self.start == other.start and self.length == other.length
    
    def __iter__(self):
        yield self.start
        yield self.length
        
    def __len__(self):
        return self.length
    
    def __repr__(self):
        return "<%s start:%s length:%s>" % (object.__repr__(self).split()[0][1:], self.start, self.length)
    
    def __hash__(self):
        return hash((self.__class__, self.start, self.length))
    
    def copy(self):
        return Region(self.start, self.length)
    
    def overlap(self, region):
        start = max(self.start, region.start)
        length = min(region.start + region.length, self.start + self.length) - start
        if length > 0:
            return Region(start, length)
         
    def merge(self, region):
        start = min(self.start, region.start)
        length = max(region.start + region.length, self.start + self.length) - start
        self.start = start
        self.length = length
                    
class RegionSelection(Component):
    __gproperties__ = dict(
        regions = (
            gobject.TYPE_PYOBJECT,
            'regions',
            'selected regions',
            gobject.PARAM_READWRITE))
    
    def __init__(self):
        Component.__init__(self)
        self.regions = []
    
    regions = prop('regions')
    
    def __len__(self):
        return len(self.regions)

    def incorporate(self, region):
        i = 0
        while i < len(self):
            if region.overlap(self.regions[i]):
                region.merge(self.regions.pop(i))
                continue
            i += 1
        self.regions.append(region)
        self.emit('changed', Change())
    
    def clear(self):
        while self.regions:
            self.regions.pop()
        self.emit('changed', Change())
        
    def get_region(self, value):
        for region in self.regions:
            if value in region:
                return region
    
    def add(self, regions):
        if isinstance(regions, Region):
            regions = [regions]
        self.regions.extend(r for r in regions if not r in self.regions)
        self.emit('changed', [Change('regions', 'region-added', regions)])
        
    def add_region(self, start, length):
        region = Region(start, length)
        self.regions.append(region)
        self.emit('changed', [Change('regions', 'region-added', region)])
        return region

    def remove(self, region):
        self.regions.remove(region)
        self.emit('changed', [Change('regions', 'region-removed', region)])
        
    def update_region(self, region, start, length):
        old = region.copy()
        region.start = start
        region.length = length
        self.emit('changed', [Change('regions', 'region-changed', (old, region))])
        
    def get_indexes(self):
        return sum((range(r.start, r.start + r.length) for r in self.regions), [])

    def invert(self, size):
        i = 0
        regions = []
        for region in sorted(self.regions,key=lambda r: r.start):
            length = region.start - i
            if length > 0:
                regions.append(Region(i, length))
            i = max(i, region.start + region.length)
        length = size - i
        if length > 0:
            regions.append(Region(i, length))
        self.regions = regions
                            
                
class Area(object):
    def __init__(self, positions, sequences):        
        self.positions = positions
        self.sequences = sequences

    def __iter__(self):
        yield self.positions.start
        yield self.sequences.start
        yield self.positions.length
        yield self.sequences.length

    @classmethod
    def from_rect(self, position, sequence, width, height):
        p = Region(position, width)
        s = Region(sequence, height)
        return Area(p, s)
    
    def __contains__(self, (position, sequence)):
        return position in self.positions and sequence in self.sequences

    def copy(self):
        positions = self.positions.copy()
        sequences = self.sequences.copy()
        return Area(positions, sequences)

    def __eq__(self, area):
        return self.positions == area.positions and self.sequences == area.sequences
    
    def __len__(self):
        return len(self.positions) * len(self.sequences)

    def overlap(self, area):
        positions = self.positions.overlap(area.positions)
        sequences = self.sequences.overlap(area.sequences)
        if positions and sequences:
            return Area(positions, sequences)

    def merge(self, area):
        self.positions.merge(area.positions)
        self.sequences.merge(area.sequences)

class AreaSelection(Component):
    __gproperties__ = dict(
        areas = (
            gobject.TYPE_PYOBJECT,
            'areas',
            'selected areas',
            gobject.PARAM_READWRITE))
    
    def __init__(self):
        Component.__init__(self)
        self.areas = []
    
    areas = prop('areas')
        
    def __len__(self):
        return len(self.areas)

    def clear(self):
        while self.areas:
            self.areas.pop()
        self.emit('changed', Change())
            
    def get_area(self, position, sequence):
        for area in self.areas:
            if (position, sequence) in area:
                return area 

    def add(self, areas):
        if isinstance(areas, Area):
            areas = [areas]
        self.areas.extend(a for a in areas if not a in self.areas)
        self.emit('changed', [Change('areas', 'area-added', areas)])

    def add_area(self, position, sequence, width, height):
        area = Area.from_rect(position, sequence, width, height)
        self.areas.append(area)
        self.emit('changed', [Change('areas', 'area-added', area)])
        return area

    def remove(self, area):
        self.areas.remove(area)
        self.emit('changed', [Change('areas', 'area-removed', area)])

    def update_area(self, area, position, sequence, width, height):
        old = area.copy()
        area.positions.start = position
        area.positions.length = width
        area.sequences.start = sequence
        area.sequences.length = height
        self.emit('changed', [Change('areas', 'area-changed', (old, area))])

class Selection(Component):
    __gproperties__ = dict(
        msa = (
            gobject.TYPE_PYOBJECT,
            'msa',
            'The msa that the selection refers to',
            gobject.PARAM_READWRITE),
        areas = (
            gobject.TYPE_PYOBJECT,
            'areas',
            'area selection',
            gobject.PARAM_READABLE),
        positions = (
            gobject.TYPE_PYOBJECT,
            'positions',
            'position selection',
            gobject.PARAM_READABLE),
        sequences = (
            gobject.TYPE_PYOBJECT,
            'sequences',
            'sequence selection',
            gobject.PARAM_READABLE))
    
    def __init__(self, msa=None):
        Component.__init__(self)
        self.msa = msa
        
    def __len__(self):
        return len(self.positions) + len(self.sequences) + len(self.areas)

    msa = prop('msa')
    areas = prop('areas', readonly=True)
    positions = prop('positions', readonly=True)
    sequences = prop('sequences', readonly=True)

    def handle_msa_change(self, msa, change):
        if not change.has_changed('sequences'):
            return
        d = dict(areas=AreaSelection(), 
                 positions=RegionSelection(), 
                 sequences=RegionSelection())
        handler = self.forward_selection_part_changes
        self.propvalues.update(d)
        for name, source in d.items():
            try:
                self.connections.pop(name).disconnect()
            except KeyError:
                pass
            self.connections[name] = Connection.change_handler(source, handler, args=['name'])
        self.emit('changed', Change())

    def forward_selection_part_changes(self, part, change, name):
        self.emit('changed', Change(name, data=[part, change]))

    def do_set_property_msa(self, pspec, msa):
        self.propvalues['msa'] = msa
        self.handle_msa_change(msa, Change())
        
    def invert_positions(self):
        self.positions.invert(len(self.msa))

    def invert_sequences(self):
        self.sequences.invert(len(self.msa.sequences))

    def clear(self):
        self.positions.clear()
        self.sequences.clear()
        self.areas.clear()
    
        