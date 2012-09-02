"""MSAView - Backbone rendering support.

Copyright (c) 2011 Joel Hedlund.

Contact: Joel Hedlund <yohell@ifm.liu.se>

MSAView is a modular, configurable and extensible package for analysing and 
visualising multiple sequence alignments and sequence features. 

This package provides support for rendering sequences as (dashed/gapped) 
backbones. Good for boxes-on-string representation of sequence features. 
 
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

import msaview

from msaview.component import Change
from msaview.plotting import vector_based
from msaview.selection import Region 
from msaview.features import (ContiguousRegion, 
                              make_regions)

class BackboneRenderer(msaview.renderers.MSARenderer):

    def __init__(self):
        msaview.renderers.MSARenderer.__init__(self)
        self.backbones = None
        self.gaps = None
        
    msaview_classname = 'renderer.msa.backbone'
    
    def handle_msa_change(self, msa, change):
        if not change.has_changed('sequences'):
            return
        if msa.ungapped is None:
            self.backbones = None
            self.gaps = None
            return
        self.backbones = [ContiguousRegion(make_regions(u, bool)) for u in msa.ungapped]
        self.gaps = []
        for backbone in self.backbones:
            gap_parts = []
            previous = None
            for part in backbone.parts:
                if previous is None:
                    previous = part
                    continue
                gap_start = previous.start + previous.length
                gap_parts.append(Region(gap_start, part.start - gap_start))
            self.gaps.append(ContiguousRegion(gap_parts))
        self.emit('changed', Change('visualization'))
        
    def render(self, cr, area):
        if not self.backbones:
            return
        if (area.total_width < len(self.msa) or
            area.total_height < len(self.msa.sequences)):
            # Probably should return here, may look ugly.
            pass
        raster_backend = not vector_based(cr)
        msa_area = area.msa_area(self.msa)
        def draw_lines(contiguous_regions, linewidth):
            for seq in range(msa_area.sequences.start, msa_area.sequences.start + msa_area.sequences.length):
                y = (seq + 0.5) / len(self.msa.sequences) * area.total_height - area.y
                if raster_backend:
                    y = int(y - linewidth / 2) + linewidth / 2
                for region in contiguous_regions[seq].parts:
                    if region.start + region.length < msa_area.positions.start:
                        continue
                    if region.start > msa_area.positions.start + msa_area.positions.length:
                        break
                    x_start = float(region.start) / len(self.msa) * area.total_width - area.x
                    x_stop = float(region.start + region.length) / len(self.msa) * area.total_width - area.x
                    if raster_backend:
                        x_start = int(x_start)
                        x_stop = int(x_stop)
                    cr.move_to(x_start, y)
                    cr.line_to(x_stop, y)
        linewidth = min(2, max(10, float(area.total_height) / len(self.msa.sequences) / 2))
        if raster_backend:
            linewidth = int(linewidth)
        cr.save()
        cr.rectangle(0, 0, area.width, area.height)
        cr.clip()
        cr.set_source_rgba(0, 0, 0, self.alpha)
        cr.save()
        cr.set_line_width(linewidth/2)
        cr.set_dash([1, 1])
        draw_lines(self.gaps, int(linewidth/2))
        cr.stroke()
        cr.restore()
        cr.set_line_width(linewidth)
        draw_lines(self.backbones, linewidth)
        cr.stroke()
        cr.restore()
            
class BackboneRendererSetting(msaview.preset.ComponentSetting):
    component_class = BackboneRenderer

msaview.presets.register_component_defaults(BackboneRendererSetting)
