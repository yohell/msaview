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
