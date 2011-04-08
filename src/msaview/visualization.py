import math
import os
import warnings

import cairo
import gobject
import gtk
import pango
import pangocairo

from adjustments import (MsaviewAdjustment, 
                         ZoomAdjustment)
from color import (Color, 
                   ColorSetting)
from action import (Action,
                    register_action)
from component import (Change, 
                       Component, 
                       prop)
from preset import (ComponentSetting,
                    IntSetting,
                    SettingComponentList,
                    SettingList,
                    presets)
from msa import BoundaryOption
from options import (BooleanOption,
                     ColorOption,
                     ComponentListOption, 
                     FontOption,
                     IntOption,
                     Option,
                     _UNSET)
from overlays import Overlay
from renderers import (RenderArea, 
                       Renderer, 
                       RendererStack)

# May be overridden by later preset definitions, for example in in preset files.
presets.add_builtin('color:background_default', Color(1, 1, 1))

class View(Component):
    __gproperties__ = dict(
        background = (
            gobject.TYPE_PYOBJECT,
            'background',
            'the background color',
            gobject.PARAM_READWRITE),
        hadjustment = (
            gobject.TYPE_PYOBJECT,
            'the horizontal adjustment',
            'the adjustment governing the horizontal behavior of the view',
            gobject.PARAM_READWRITE),
        vadjustment = (
            gobject.TYPE_PYOBJECT,
            'the vertical adjustment',
            'the adjustment governing the vertical behavior of the view',
            gobject.PARAM_READWRITE),
        renderers = (
            gobject.TYPE_PYOBJECT,
            'renderers',
            'renderer stack for view agnostic, static, cacheable parts of the view',
            gobject.PARAM_READWRITE),
        overlays = (
            gobject.TYPE_PYOBJECT,
            'overlays',
            'renderers for view aware things, dynamically drawn on top of the static parts',
            gobject.PARAM_READWRITE),
        width_request = (
            gobject.TYPE_INT,
            'preferred view width',
            'the preferred width of the view',
            -1,
            100000,
            -1,
            gobject.PARAM_READWRITE),
        height_request = (
            gobject.TYPE_INT,
            'preferred view height',
            'the preferred height of the view',
            -1,
            100000,
            -1,
            gobject.PARAM_READWRITE),
            )
    
    propdefaults = dict(background=presets.get_setting('color:background_default'),
                        height_request=-1,
                        overlays=[],
                        renderers=RendererStack(),
                        width_request=-1)
    
    def __init__(self, hadjustment=None, vadjustment=None):
        Component.__init__(self)
        if hadjustment is None:
            hadjustment = ZoomAdjustment()
            hadjustment.zoom_to_fit(800)
        if vadjustment is None:
            vadjustment = ZoomAdjustment()
            vadjustment.zoom_to_fit(600)
        self.propvalues.update(hadjustment=hadjustment,
                               vadjustment=vadjustment)

    def reset(self):
        Component.reset(self)
        self.propvalues['renderers'] = RendererStack()

    background = prop('background')
    renderers = prop('renderers')
    overlays = prop('overlays')
    hadjustment = prop('hadjustment')
    vadjustment = prop('vadjustment')
    width_request = prop('width_request')
    height_request = prop('height_request')

    def do_set_property(self, pspec, value):
        name = pspec.name.replace('-', '_')
        if name in ['width_request', 'height_request', 'hadjustment', 'vadjustment']:
            if value != getattr(self, name):
                self.propvalues[name] = value
                self.emit('changed', Change(name))
            return
        if name in ['renderers', 'overlays']:
            if value != getattr(self, name):
                self.propvalues[name] = value
                self.emit('changed', Change('visualization'))
            return
        Component.do_set_property(self, pspec, value) 

    def forward_visualization_changes(self, renderer, change, type):
        if not change.has_changed('visualization'):
            return
        self.emit('changed', Change('visualization', type, change))

    def handle_descendant_removed(self, component, descendant):
        if descendant in self.children:
            if isinstance(descendant, Renderer):
                key = 'overlays' if isinstance(descendant, Overlay) else 'renderers'
                l = getattr(self, key)    # self.overlays is a plain list while
                l = getattr(l, key, l) # self.renderers is a renderer stack...
                i = l.index(descendant)
                l.pop(i) 
                descendant.disconnect(self.connections[key].pop(i))
                self.emit('changed', Change('visualization', '%s_removed' % key, descendant))
        Component.handle_descendant_removed(self, component, descendant)
        
    def _get_view_area(self):
        if not (self.hadjustment.upper and self.vadjustment.upper):
            return None
        return RenderArea(self.hadjustment.value, 
                          self.vadjustment.value, 
                          self.hadjustment.page_size, 
                          self.vadjustment.page_size,
                          self.hadjustment.upper, 
                          self.vadjustment.upper)

    def draw(self, cr, area=None):
        if area is None:
            if self.hadjustment:
                width = int(self.hadjustment.page_size)
            else:
                width = self.width_request
            if self.vadjustment:
                height = int(self.vadjustment.page_size)
            else:
                height = self.height_request
            area = gtk.gdk.Rectangle(0, 0, width, height)
        cr.rectangle(*area)
        cr.clip()
        if self.background:
            cr.set_source_rgba(*self.background.rgba)
            cr.paint()
        render_area = RenderArea.from_view_area(self, area)
        self.renderers.render(cr, render_area)
        for overlay in self.overlays:
            cr.save()
            overlay.draw(cr, area)
            cr.restore()

    def render(self, cr, view_area=None):
        if view_area is None:
            view_area = self._get_view_area()
        cr.rectangle(0, 0, view_area.width, view_area.height)
        cr.clip()
        if self.background:
            cr.set_source_rgba(*self.background.rgba)
            cr.paint()
        self.renderers.render(cr, view_area)
        for overlay in self.overlays:
            cr.save()
            overlay.render(cr, view_area)
            cr.restore()

    def add_renderers(self, renderers):
        if isinstance(renderers, Renderer):
            renderers = [renderers]
        cb = self.forward_visualization_changes
        self.connections.setdefault('renderers', []).extend(r.connect('changed', cb, 'renderer_changed') for r in renderers)
        if not self.renderers:
            self.renderers = RendererStack()
        self.renderers.renderers.extend(renderers)
        self.emit('changed', Change('visualization', 'renderers_added', renderers))

    def add_overlays(self, overlays):
        if isinstance(overlays, Overlay):
            overlays = [overlays]
        cb = self.forward_visualization_changes
        self.connections.setdefault('overlays', []).extend(o.connect('changed', cb, 'overlay_changed') for o in overlays)
        if not self.overlays:
            self.overlays = []
        self.overlays.extend(overlays)
        self.emit('changed', Change('visualization', 'overlays_added', overlays))
        
    def get_options(self):
        return [ComponentListOption(self, 'renderers', self.renderers.renderers),
                ComponentListOption(self, 'overlays')]

    def zoom_step(self, steps, xfocus=0.5, yfocus=0.5):
        self.hadjustment.zoom_step(steps, xfocus)
        self.vadjustment.zoom_step(steps, yfocus)

    def zoom_to_fit(self):
        self.hadjustment.zoom_to_fit(self.hadjustment.page_size)
        self.vadjustment.zoom_to_fit(self.vadjustment.page_size)

    def get_detail_size(self):
        detail_sizes = (r.get_detail_size() for r in self.renderers)
        return [max(t) for t in zip(*detail_sizes) if t] or [0, 0]

    def zoom_to_details(self, fill=False):
        width, height = self.get_detail_size()
        if fill:
            width = max(width, self.hadjustment.page_size)
            height = max(height, self.vadjustment.page_size)
        self.hadjustment.zoom_to_size(width)
        self.vadjustment.zoom_to_size(height)
        
    def add(self, child, name=None):
        if isinstance(child, Overlay):
            self.add_overlays(child)
        elif isinstance(child, Renderer):
            self.add_renderers(child)
        return Component.add(self, child, name)
        
    def integrate(self, ancestor, name=None):
        layout = ancestor.find_descendant('layout')
        if layout is None:
            layout = presets.get_preset('layout').component_class()
            if not layout.integrate(ancestor):
                raise TypeError('no suitable parent')
        d = dict(hadjustment=layout.hadjustment, vadjustment=layout.vadjustment)
        self.propvalues.update(d)
        self.msaview_name = layout.add(self, name)
        self.emit('changed', Change(d.keys()))
        return self.msaview_name
    
class MSAView(View):
    __gproperties__ = dict(
        msa = (
            gobject.TYPE_PYOBJECT,
            'msa',
            'the multiple sequence alignment to visualize',
            gobject.PARAM_READWRITE))
    msaview_classname = 'view.msa'
    msa = prop('msa')

    def integrate(self, ancestor, name=None):
        layout = ancestor.find_descendant('layout')
        if layout is None:
            layout = presets.get_preset('layout').component_class()
            if not layout.integrate(ancestor):
                raise TypeError('no suitable parent')
        d = dict(hadjustment=layout.hadjustment, 
                 vadjustment=layout.vadjustment,
                 msa=layout.find_ancestor('data.msa'))
        self.propvalues.update(d)
        self.msaview_name = layout.add(self, name)
        self.emit('changed', Change(d.keys()))
        return self.msaview_name
    
    
class RendererListSetting(SettingComponentList):
    tag = 'renderer'
    
class OverlayListSetting(SettingComponentList):
    tag = 'overlay'
    
class ViewSetting(ComponentSetting):
    setting_types = dict(background=ColorSetting,
                         height_request=IntSetting,
                         overlays=OverlayListSetting,
                         renderers=RendererListSetting,
                         width_request=IntSetting)

class MSAViewSetting(ViewSetting):
    component_class = MSAView
presets.register_component_defaults(MSAViewSetting)
s = MSAViewSetting(dict(overlays=OverlayListSetting([presets.get_setting('overlay.selection'),
                                                     presets.get_setting('overlay.locator')])))
presets.add_preset('view.msa:standard', s, builtin=True)

class ZoomAreaAction(Action):
    action_name = 'zoom-area'
    path = ['Zoom', 'Zoom to area']
    tooltip = 'Zoom to area.'
    
    @classmethod
    def applicable(cls, target=None, coord=None):
        if target.msaview_classname == 'layout':
            if not target.msaviews:
                return
            target = target.msaviews[0]
        if target.msaview_classname != 'view.msa':
            return
        if not target.msa:
            return
        return cls(target, coord)
            
    def get_options(self):
        return [BoundaryOption(propname='position-start', value=None, default=None, nick='Start', tooltip='Index or motif start boundary in the range.'),
                BoundaryOption(propname='position-end', value=None, default=None, nick='End', tooltip='Index or motif for the end boundary in the range.'),
                BoundaryOption(propname='reference', value=None, default=None, nick='Reference sequence', tooltip='Sequence ID or index; treat indexes/motifs relative to this sequence instead of the MSA.'),
                BoundaryOption(propname='sequence-start', value=None, default=None, nick='Sequence Start', tooltip='Index or ID for the first sequence in the range.'),
                BoundaryOption(propname='sequence-end', value=None, default=None, nick='Sequence End', tooltip='Index or ID for the last sequence in the range.'),
                BooleanOption(propname='regex', default=True, value=True, nick='Regular Expression', tooltip='Use regular expressions to match sequence identifiers.')]
    
    def run(self):
        reference_index = None
        reference = self.params['reference'] and self.params['reference'].strip()
        if reference:
            try:
                reference = int(reference)
            except ValueError:
                pass
            reference_index = self.target.msa.get_sequence_index(reference, self.params['regex'])
        a = self.target.msa.get_area(self.params['position-start'], 
                                     self.params['position-end'], 
                                     self.params['sequence-start'], 
                                     self.params['sequence-end'], 
                                     reference_index, 
                                     self.params['regex'])
        if not self.target.hadjustment.page_size:
            self.target.hadjustment.page_size = 640
        if not self.target.vadjustment.page_size:
            self.target.vadjustment.page_size = 480
        total_width = int(self.target.hadjustment.page_size / a.positions.length * len(self.target.msa))
        total_height = int(self.target.vadjustment.page_size / a.sequences.length * len(self.target.msa.sequences))
        x = int(float(a.positions.start - 1) / len(self.target.msa) * total_width)
        y = int(float(a.sequences.start - 1) / len(self.target.msa.sequences) * total_height)
        self.target.hadjustment.zoom_to_size(total_width)
        self.target.hadjustment.value = x
        self.target.vadjustment.zoom_to_size(total_height)
        self.target.vadjustment.value = y
        
register_action(ZoomAreaAction)
    
class ZoomSequencesAction(Action):
    action_name = 'zoom-sequences'
    path = ['Zoom', 'Zoom sequences']
    tooltip = 'Zoom to sequence region.'
    
    @classmethod
    def applicable(cls, target=None, coord=None):
        if target.msaview_classname == 'layout':
            if not target.msaviews:
                return
            target = target.msaviews[0]
        if target.msaview_classname not in ['view.msa', 'view.seq']:
            return
        if not target.msa:
            return
        return cls(target, coord)
            
    def get_options(self):
        return [BoundaryOption(propname='start', value=None, default=None, nick='Start', tooltip='Index or ID for the first sequence in the range.'),
                BoundaryOption(propname='end', value=None, default=None, nick='End', tooltip='Index or ID for the last sequence in the range.'),
                BooleanOption(propname='regex', default=True, value=True, nick='Regular Expression', tooltip='Use regular expressions to match sequence identifiers.')]
    
    def run(self):
        r = self.target.msa.get_sequence_region(self.params['start'], self.params['end'], self.params['regex'])
        total_height = int(self.target.vadjustment.page_size / r.length * len(self.target.msa.sequences))
        y = int(float(r.start) / len(self.target.msa.sequences) * total_height)
        self.target.vadjustment.zoom_to_size(total_height)
        self.target.vadjustment.value = y
    
register_action(ZoomSequencesAction)

class ZoomPositionsAction(Action):
    action_name = 'zoom-positions'
    path = ['Zoom', 'Zoom positions']
    tooltip = 'Zoom to position region.'
    
    @classmethod
    def applicable(cls, target=None, coord=None):
        if target.msaview_classname == 'layout':
            if not target.msaviews:
                return
            target = target.msaviews[0]
        if target.msaview_classname not in ['view.msa', 'view.pos']:
            return
        if not target.msa:
            return
        return cls(target, coord)
            
    def get_options(self):
        return [BoundaryOption(propname='start', value=None, default=None, nick='Start', tooltip='Index or ID for the first sequence in the range.'),
                BoundaryOption(propname='end', value=None, default=None, nick='End', tooltip='Index or ID for the last sequence in the range.'),
                BoundaryOption(propname='reference', value=None, default=None, nick='Reference sequence', tooltip='Sequence ID or index; treat indexes/motifs relative to this sequence instead of the MSA.'),
                BooleanOption(propname='regex', default=True, value=True, nick='Regular Expression', tooltip='Use regular expressions to match sequence identifiers.')]
    
    def run(self):
        sequence_index = None
        reference = self.params['reference'] and self.params['reference'].strip()
        if reference:
            try:
                reference = int(reference)
            except ValueError:
                pass
            sequence_index = self.target.msa.get_sequence_index(reference, self.params['regex'])
        r = self.target.msa.get_position_region(self.params['start'], self.params['end'], sequence_index)
        total_width = int(self.target.hadjustment.page_size / r.length * len(self.target.msa))
        x = int(float(r.start) / len(self.target.msa) * total_width)
        self.target.hadjustment.zoom_to_size(total_width)
        self.target.hadjustment.value = x
    
register_action(ZoomPositionsAction)
    
class ZoomStepsAction(Action):
    action_name = 'zoom-steps'
    path = ['Zoom', 'Zoom steps']
    tooltip = 'Zoom in a number of steps.'

    @classmethod
    def applicable(cls, target=None, coord=None):
        if target.msaview_classname == 'layout':
            if not target.msaviews:
                return
            target = target.msaviews[0]
        if not target.msaview_classname.startswith('view.'):
            return
        if not target.msa:
            return
        return cls(target, coord)

    def get_options(self):
        return [IntOption(propname='steps', minimum=-10000, maximum=10000, default=1, value=1, nick='Steps', tooltip="Number of steps to zoom in (negative to zoom out).")]

    def run(self):
        self.target.zoom_step(self.params['steps'])
    
register_action(ZoomStepsAction)

class ZoomToFitAction(Action):
    action_name = 'zoom-to-fit'
    path = ['Zoom', 'Zoom to fit']
    tooltip = 'Zoom to fit the MSA in the current view.'

    @classmethod
    def applicable(cls, target=None, coord=None):
        if target.msaview_classname == 'layout':
            if not target.msaviews:
                return
            target = target.msaviews[0]
        if not target.msaview_classname.startswith('view.'):
            return
        if not target.msa:
            return
        return cls(target, coord)

    def run(self):
        self.target.zoom_to_fit()
    
register_action(ZoomToFitAction)

class PosView(MSAView):
    __gproperties__ = dict(
        height_request = (
            gobject.TYPE_INT,
            'height request',
            'the preferred height of the view',
            -1,
            100000,
            50,
            gobject.PARAM_READWRITE))
    
    msaview_classname = 'view.pos'
    propdefaults = dict(View.propdefaults,
                        height_request=50)
    
    def __init__(self, hadjustment=None):
        vadjustment = MsaviewAdjustment()
        View.__init__(self, hadjustment, vadjustment)
        vadjustment.upper = self.height_request
        vadjustment.page_size = self.height_request

    def do_set_property(self, pspec, value):
        name = pspec.name.replace('-', '_')
        if name == 'height_request':
            if value != getattr(self, name):
                adj = self.vadjustment
                self.propvalues[name] = value
                adj.page_size = value
                adj.upper = value
                adj.emit('value-changed')
                self.emit('changed', Change(name))
            return
        View.do_set_property(self, pspec, value)

    def get_options(self):
        return View.get_options(self) + [IntOption(self, 'height_request', hint_maximum=400, hint_step=10)]

    def set_options(self, options):
        for option in options:
            if option.propname == 'renderers':
                # FIXME: Deal with renderers being set.
                continue
            setattr(self.props, option.propname, option.value)

    def zoom_step(self, steps, focus=0.5):
        self.hadjustment.zoom_step(steps, focus)

    def zoom_to_fit(self):
        self.hadjustment.zoom_to_fit(self.hadjustment.page_size)

    def get_detail_size(self):
        detail_sizes = (r.get_detail_size() for r in self.renderers)
        return [max(t) for t in zip(*detail_sizes) if t] or [0, 0]

    def zoom_to_details(self, fill=False):
        width, height = self.get_detail_size()
        if fill:
            width = max(width, self.hadjustment.page_size)
        self.hadjustment.zoom_to_size(width)
        
    def integrate(self, ancestor, name=None):
        layout = ancestor.find_descendant('layout')
        if layout is None:
            layout = presets.get_preset('layout').component_class()
            if not layout.integrate(ancestor):
                raise TypeError('no suitable parent')
        self.hadjustment = layout.hadjustment
        self.msa = layout.find_ancestor('data.msa')
        self.msaview_name = layout.add(self, name)
        return self.msaview_name

class PosViewSetting(ViewSetting):
    component_class = PosView

presets.register_component_defaults(PosViewSetting)
s = PosViewSetting(dict(overlays=OverlayListSetting([presets.get_setting('overlay.selection'),
                                                     presets.get_setting('overlay.locator')])))
presets.add_preset('view.pos:standard', s)

class SeqView(MSAView):
    __gproperties__ = dict(
        width_request = (
            gobject.TYPE_INT,
            'width request',
            'the preferred width of the view',
            -1,
            100000,
            50,
            gobject.PARAM_READWRITE))

    msaview_classname = 'view.seq'
    propdefaults = dict(View.propdefaults,
                        width_request=50)
    
    def __init__(self, vadjustment=None):
        hadjustment = MsaviewAdjustment()
        View.__init__(self, hadjustment, vadjustment)        
        hadjustment.upper = self.width_request
        hadjustment.page_size = self.width_request

    def do_set_property(self, pspec, value):
        name = pspec.name.replace('-', '_')
        if name == 'width_request':
            if value != getattr(self, name):
                adj = self.hadjustment
                self.propvalues[name] = value
                adj.page_size = value
                adj.upper = value
                adj.emit('value-changed')
                self.emit('changed', Change(name))
            return
        View.do_set_property(self, pspec, value)

    def get_options(self):
        return View.get_options(self) + [IntOption(self, 'width_request', hint_maximum=600, hint_step=10)]

    def set_options(self, options):
        for option in options:
            if option.propname == 'renderers':
                # FIXME: Deal with renderers being set.
                continue
            setattr(self.props, option.propname, option.value)

    def zoom_step(self, steps, focus=0.5):
        self.vadjustment.zoom_step(steps, focus)

    def zoom_to_fit(self):
        self.vadjustment.zoom_to_fit(self.vadjustment.page_size)

    def get_detail_size(self):
        detail_sizes = (r.get_detail_size() for r in self.renderers)
        return [max(t) for t in zip(*detail_sizes) if t] or [0, 0]

    def zoom_to_details(self, fill=False):
        width, height = self.get_detail_size()
        if fill:
            height = max(height, self.vadjustment.page_size)
        self.vadjustment.zoom_to_size(height)
        
    def integrate(self, ancestor, name=None):
        layout = ancestor.find_descendant('layout')
        if layout is None:
            layout = presets.get_preset('layout').component_class()
            if not layout.integrate(ancestor):
                raise TypeError('no suitable parent')
        self.vadjustment = layout.vadjustment
        self.msa = layout.find_ancestor('data.msa')
        self.msaview_name = layout.add(self, name)
        return self.msaview_name

class SeqViewSetting(ViewSetting):
    component_class = SeqView

presets.register_component_defaults(SeqViewSetting)
s = SeqViewSetting(dict(overlays=OverlayListSetting([presets.get_setting('overlay.selection'),
                                                     presets.get_setting('overlay.locator')])))
presets.add_preset('view.seq:standard', s)

units = {'mm': gtk.UNIT_MM, 
         'in': gtk.UNIT_INCH, 
         'pt': gtk.UNIT_POINTS}

unit_names = {gtk.UNIT_MM: 'mm',
              gtk.UNIT_INCH: 'in',
              gtk.UNIT_POINTS: 'pt'}

unit_to_points_factors = {gtk.UNIT_MM: 2.83464566929,
                          gtk.UNIT_INCH: 72.0,
                          gtk.UNIT_POINTS: 1.0}

default_unit = gtk.UNIT_MM

def convert_to_points(value, unit):
    return value * unit_to_points_factors[unit]

def parse_paper_name(name):
    name = name.strip().lower()
    prefixes = ('', 'iso', 'na', 'asme', 'jis', 'jpn', 'prc', 'om', 'roc', 'oe')
    # passing an illegal paper name to gtk.PaperSize() issues a warning. Using 
    # warnings.filterwarnings('error') we should be able to convert this warning
    # to an exception and catch it and react to it. However, for some reason,
    # the warning issued by gtk.PaperSize() and thus converted to an exeption 
    # does not get raised until *next time* a warning is issued, presumably due
    # to a bug in pygtk (?).
    # This makes this method needlessly complicated.   
    with warnings.catch_warnings():
        warnings.filterwarnings('error')
        for prefix in prefixes:
            s = name
            if prefix:
                s = prefix + '_' + name
            try:
                paper_size = gtk.PaperSize(s)   
                warnings.warn('warning') # this should be superflous, but gtk warnings are buggy. 
            except UserWarning:
                return paper_size 
            except Warning:
                pass

def set_margins(page_setup, margins, unit=gtk.UNIT_POINTS):
    """Convenience function for setting margins on gtk.PageSetup() objects.
    
    margins: A dict with the keys ('left', 'right', 'top', 'bottom'), or optional 
        default keys ('horizontal', 'vertical') or 'all'. This can also be a list
        [all], [horizontal, vertical] or [left, right, top, bottom], or a number 
        which is equivalent to [all].
    unit: unit for the margin measurements.
     
    """
    if isinstance(margins, (int, float)):
        margins = dict(all=margins)
    elif isinstance(margins, (list, tuple)):
        if len(margins) == 1:
            margins = dict(all=margins[0])
        elif len(margins) == 2:
            margins = dict(horizontal=margins[0], vertical=margins[1])
        elif len(margins) == 4:
            margins = dict(left=margins[0], right=margins[1], top=margins[2], bottom=margins[3])
        else:
            raise ValueError('wrong number of margins in list')
    if not margins:
        return
    margins = dict(margins)
    margins.setdefault('vertical', margins['all'])
    margins.setdefault('top', margins['vertical'])
    margins.setdefault('bottom', margins['vertical'])
    margins.setdefault('horizontal', margins['all'])
    margins.setdefault('left', margins['horizontal'])
    margins.setdefault('right', margins['horizontal'])
    for direction in ('left', 'right', 'top', 'bottom'):
        value = margins[direction]
        if value is None:
            continue
        getattr(page_setup, 'set_%s_margin' % direction)(value, unit)

def get_page_area(page_setup):
    """Returns [x, y, w, h] in points, rounded to three decimals.
    
    This function is useful in order to avoid floating point precision errors 
    in gtk.PageSetup()
    """
    return [round(page_setup.get_left_margin(gtk.UNIT_POINTS), 2),
            round(page_setup.get_top_margin(gtk.UNIT_POINTS), 2),
            round(page_setup.get_page_width(gtk.UNIT_POINTS), 2),
            round(page_setup.get_page_height(gtk.UNIT_POINTS), 2)]

class WidthExtents(object):
    """Width extents for the pages in one column of a posterized layout."""
    def __init__(self, page_start_x=0, page_width=0, msaview_start_x=None, msaview_width=0, position=None, n_positions=0, seqview_start=None, n_seqviews=0, seqview_start_x=None, seqview_width=0):
        self.page_start_x = page_start_x
        self.page_width = page_width
        self.msaview_start_x = msaview_start_x
        self.msaview_width = msaview_width
        self.position = position
        self.n_positions = n_positions
        self.seqview_start = seqview_start
        self.n_seqviews = n_seqviews
        self.seqview_start_x = seqview_start_x
        self.seqview_width = seqview_width
    
    @classmethod
    def get_extents(cls, layout, msa_area, page_area, msa_render_area):
        page_widths = []
        page_x = 0
        page_start_x = 0
        n_seqviews = 0
        seqview_start = 0
        seqview_start_x = 0
        x_scale = float(msa_render_area.total_width) / msa_area[2]
        max_positions_per_page = int(page_area[2] / x_scale)
        for seqview_index, seqview in enumerate(layout.seqviews):
            if page_x + seqview.width_request > page_area[2]:
                if page_x:
                    page_widths.append(cls(page_start_x=page_start_x, 
                                           page_width=page_x, 
                                           seqview_start=seqview_start, 
                                           n_seqviews=n_seqviews, 
                                           seqview_start_x=seqview_start_x, 
                                           seqview_width=page_x))
                    page_start_x += page_x
                seqview_start = seqview_index
                seqview_start_x = 0
                n_seqviews = 1
                for i in range(int(seqview.width_request / page_area[2])):
                    page_widths.append(cls(page_start_x=page_start_x, 
                                           page_width=page_area[2], 
                                           seqview_start=seqview_index, 
                                           n_seqviews=n_seqviews, 
                                           seqview_start_x=seqview_start_x, 
                                           seqview_width=page_area[2]))
                    page_start_x += page_area[2]
                    seqview_start_x += page_area[2]
                page_x = seqview.width_request % page_area[2]
                continue
            page_x += seqview.width_request
            n_seqviews += 1
        first_position_fraction = (1 - msa_area[0] % 1)
        if page_x > page_area[2] - first_position_fraction * x_scale:
            page_widths.append(cls(page_start_x=page_start_x, 
                                   page_width=page_x, 
                                   seqview_start=seqview_start, 
                                   n_seqviews=n_seqviews, 
                                   seqview_start_x=seqview_start_x, 
                                   seqview_width=page_x))
            page_start_x += page_x
            page_x = 0
            seqview_start = None
            n_seqviews = 0
            seqview_start_x = None
        msaview_start_x = msa_render_area.x
        position = msa_area[0]
        positions_on_first_msaview_page = min(msa_area[2], int((page_area[2] - page_x - first_position_fraction * x_scale) / x_scale) + first_position_fraction)
        page_widths.append(cls(page_start_x=page_start_x, 
                               page_width=page_x + positions_on_first_msaview_page * x_scale,
                               msaview_start_x=msaview_start_x,
                               msaview_width=positions_on_first_msaview_page * x_scale,
                               position=position,
                               n_positions=positions_on_first_msaview_page,
                               seqview_start=seqview_start, 
                               n_seqviews=n_seqviews, 
                               seqview_start_x=seqview_start_x, 
                               seqview_width=page_x or None))
        page_start_x += page_x + positions_on_first_msaview_page * x_scale
        msaview_start_x = positions_on_first_msaview_page * x_scale
        position = int(round(position + positions_on_first_msaview_page, 5))
        for i in range(int((msa_area[2] - positions_on_first_msaview_page) / max_positions_per_page)):
            page_widths.append(cls(page_start_x=page_start_x, 
                                   page_width=max_positions_per_page * x_scale,
                                   msaview_start_x=msaview_start_x,
                                   msaview_width=max_positions_per_page * x_scale,
                                   position=position,
                                   n_positions=max_positions_per_page))
            page_start_x += max_positions_per_page * x_scale
            msaview_start_x += max_positions_per_page * x_scale
            position += max_positions_per_page
        if (msa_area[2] - positions_on_first_msaview_page) % max_positions_per_page:
            n_positions = (msa_area[2] - positions_on_first_msaview_page) % max_positions_per_page
            page_widths.append(cls(page_start_x=page_start_x, 
                                   page_width=n_positions * x_scale,
                                   msaview_start_x=msaview_start_x,
                                   msaview_width=n_positions * x_scale,
                                   position=position,
                                   n_positions=n_positions))
        return page_widths
    
class HeightExtents(object):
    """Height extents for the pages in one row of a posterized layout."""
    def __init__(self, page_start_y=0, page_height=0, msaview_start_y=None, msaview_height=0, sequence=None, n_sequences=None, heading_y=None, heading_height=None, posview_start=None, n_posviews=0, posview_start_y=None, posview_height=0):
        self.page_start_y = page_start_y
        self.page_height = page_height
        self.msaview_start_y = msaview_start_y
        self.msaview_height = msaview_height
        self.sequence = sequence
        self.n_sequences = n_sequences
        self.heading_y = heading_y
        self.heading_height = heading_height
        self.posview_start = posview_start
        self.n_posviews = n_posviews
        self.posview_start_y = posview_start_y
        self.posview_height = posview_height

    @classmethod
    def get_extents(cls, layout, msa_area, page_area, msa_render_area, heading_height):
        page_heights = []
        page_start_y = 0
        heading_y = 0
        y_scale = float(msa_render_area.total_height) / msa_area[3]
        max_sequences_per_page = int(page_area[3] / y_scale)
        for i in range(int(heading_height / page_area[3])):
            page_heights.append(cls(page_start_y=page_start_y,
                                    page_height=page_area[3],
                                    heading_y=heading_y,
                                    heading_height=page_area[3]))
            heading_y += page_area[3]
            page_start_y += page_area[3]
        heading_modded_height = heading_height % page_area[3]
        page_y = heading_modded_height
        first_sequence_fraction = (1 - msa_area[1] % 1)
        if page_y + first_sequence_fraction * y_scale > page_area[3]:
            page_heights.append(cls(page_start_y=page_start_y,
                                    page_height=page_y,
                                    heading_y=heading_y,
                                    heading_height=heading_modded_height))
            page_start_y += page_y
            page_y = 0
            heading_y = None
            heading_modded_height = 0
        msaview_start_y = msa_render_area.y
        sequence = msa_area[1]
        sequences_on_first_msaview_page = min(msa_area[3], int((page_area[3] - page_y - first_sequence_fraction * y_scale) / y_scale) + first_sequence_fraction)
        if sequences_on_first_msaview_page < msa_area[3]:
            page_heights.append(cls(page_start_y=page_start_y,
                                    page_height=page_y + sequences_on_first_msaview_page * y_scale,
                                    msaview_start_y=msaview_start_y,
                                    msaview_height=sequences_on_first_msaview_page * y_scale,
                                    sequence=sequence,
                                    n_sequences=sequences_on_first_msaview_page,
                                    heading_y=heading_y,
                                    heading_height=heading_modded_height))
            page_start_y += page_y + sequences_on_first_msaview_page * y_scale
            msaview_start_y += sequences_on_first_msaview_page * y_scale
            sequence = int(round(sequence + sequences_on_first_msaview_page, 5))
            heading_modded_height = 0
            for i in range(int((msa_area[3] - sequences_on_first_msaview_page) / max_sequences_per_page)):
                page_heights.append(cls(page_start_y=page_start_y,
                                        page_height=max_sequences_per_page * y_scale,
                                        msaview_start_y=msaview_start_y,
                                        msaview_height=max_sequences_per_page * y_scale,
                                        sequence=sequence,
                                        n_sequences=max_sequences_per_page))
                page_start_y += max_sequences_per_page * y_scale
                msaview_start_y += max_sequences_per_page * y_scale
                sequence += max_sequences_per_page
            n_sequences = (msa_area[3] - sequences_on_first_msaview_page) % max_sequences_per_page
        else:
            n_sequences = sequences_on_first_msaview_page
        msaview_height = n_sequences * y_scale
        page_y = n_sequences * y_scale
        posview_start = 0
        n_posviews = 0
        posview_start_y = 0
        posview_height = 0
        for posview_index, posview in enumerate(layout.posviews):
            if page_y + posview.height_request > page_area[3]:
                if page_y:
                    page_heights.append(cls(page_start_y=page_start_y,
                                            page_height=page_y,
                                            msaview_start_y=msaview_start_y,
                                            msaview_height=n_sequences * y_scale - heading_modded_height,
                                            sequence=sequence,
                                            n_sequences=n_sequences,
                                            heading_y=heading_y,
                                            heading_height=heading_modded_height,
                                            posview_start=posview_start if n_posviews else None,
                                            n_posviews=n_posviews,
                                            posview_start_y=posview_start_y,
                                            posview_height=posview_height))
                    page_start_y += page_y
                    msaview_start_y = None
                    n_sequences = 0
                    sequence = None
                    heading_y = None
                    heading_modded_height = 0
                posview_start = posview_index
                n_posviews = 1
                posview_start_y = 0
                for i in range(int(posview.height_request / page_area[3])):
                    page_heights.append(cls(page_start_y=page_start_y,
                                            page_height=page_area[3],
                                            posview_start=posview_start,
                                            n_posviews=n_posviews,
                                            posview_start_y=posview_start_y,
                                            posview_height=page_area[3]))
                    page_start_y += page_area[3]
                    posview_start_y += page_area[3]
                page_y = posview.height_request % page_area[3]
                continue
            page_y += posview.height_request
            posview_height += posview.height_request
            n_posviews += 1
        if page_y:
            page_heights.append(cls(page_start_y=page_start_y,
                                    page_height=page_y,
                                    msaview_start_y=msaview_start_y,
                                    msaview_height=n_sequences * y_scale - heading_modded_height,
                                    sequence=sequence,
                                    n_sequences=n_sequences,
                                    heading_y=heading_y,
                                    heading_height=heading_modded_height,
                                    posview_start=posview_start if n_posviews else None,
                                    n_posviews=n_posviews,
                                    posview_start_y=posview_start_y,
                                    posview_height=posview_height))
        return page_heights

class Layout(Component):
    __gproperties__ = dict(
        width=(gobject.TYPE_PYOBJECT,
            'width',
            'total horizontal size in pixels',
            gobject.PARAM_READWRITE),
        height=(gobject.TYPE_PYOBJECT,
            'height',
            'total vertical size in pixels',
            gobject.PARAM_READWRITE),
        seqview_width=(gobject.TYPE_INT,
            'seqview width',
            'total horizontal pixel size reserved for seqviews',
            -1,
            1000000,
            0,
            gobject.PARAM_READWRITE),
        posview_height=(gobject.TYPE_INT,
            'posview height',
            'total vertical pixel size reserved for posviews',
            -1,
            1000000,
            0,
            gobject.PARAM_READWRITE),
        hadjustment=(gobject.TYPE_PYOBJECT,
            'horizontal adjustment',
            'the adjustment governing the horizontal behavior of the view',
            gobject.PARAM_READWRITE),
        vadjustment=(gobject.TYPE_PYOBJECT,
            'vertical adjustment',
            'the adjustment governing the vertical behavior of the view',
            gobject.PARAM_READWRITE),
        msaviews=(gobject.TYPE_PYOBJECT,
            'msa views',
            'multiple sequence alignment visualizers',
            gobject.PARAM_READWRITE),
        posviews=(gobject.TYPE_PYOBJECT,
            'posviews',
            'visualizers for properties of positions',
            gobject.PARAM_READWRITE),
        seqviews=(gobject.TYPE_PYOBJECT,
            'seqviews',
            'visualizers for properties of sequences',
            gobject.PARAM_READWRITE),
        )
    
    msaview_classname = 'layout'
    propdefaults = dict(height=-1,
                        msaviews=[],
                        posviews=[],
                        #posview_height=-1,
                        seqviews=[],
                        #seqview_width=-1,
                        width=-1)
    def __init__(self, hadjustment=None, vadjustment=None):
        Component.__init__(self)
        if hadjustment is None:
            hadjustment = ZoomAdjustment()
            hadjustment.zoom_to_fit(800)
        if vadjustment is None:
            vadjustment = ZoomAdjustment()
            vadjustment.zoom_to_fit(600)
        self.propvalues.update(hadjustment=hadjustment, 
                               vadjustment=vadjustment, 
                               msaviews=[],
                               posviews=[],
                               seqviews=[])
        
    width = prop('width')
    height = prop('height')
    seqview_width = prop('seqview_width')
    posview_height = prop('posview_height')
    hadjustment = prop('hadjustment')
    vadjustment = prop('vadjustment')
    msaviews = prop('msaviews')
    posviews = prop('posviews')
    seqviews = prop('seqviews')

    def do_set_property(self, pspec, value):
        name = pspec.name.replace('-', '_')
        if name in ['width', 'height', 'seqview_width', 'posview_height', 'hadjustment', 'vadjustment']:
            if value != getattr(self, name):
                self.propvalues[name] = value
                self.emit('changed', Change(name))
            return
        # I'm not really sure whether or not I should make this distinction, 
        # or if I should make these guys react the same way as the other props.
        if name in ['msaviews', 'posviews', 'seqviews']:
            if value != getattr(self, name):
                self.propvalues[name] = value
                self.emit('changed', Change('visualization'))
            return
        Component.do_set_property(self, pspec, value) 
    
    def handle_descendant_removed(self, component, descendant):
        if descendant in self.children:
            i = self.children.index(descendant)
            self.children.pop(i)
            for handler_id in self.connections['children'].pop(i):
                descendant.disconnect(handler_id)
            if descendant.msaview_classname == 'view.pos':
                self.remove_posview(descendant)
            elif descendant.msaview_classname == 'view.seq':
                self.remove_seqview(descendant)
            elif descendant.msaview_classname == 'view.msa':
                self.remove_msaview(descendant)
        self.emit('descendant_removed', descendant)

    def remove_msaview(self, msaview):
        i = self.msaviews.index(msaview)
        msaview.disconnect(self.connections['msaviews'].pop(i))
        del self.msaviews[i]
        self.emit('changed', Change(['visualization', 'msaviews'], 'msaview_removed', i))

    def remove_posview(self, posview):
        self.propvalues['posview_height'] -= posview.height_request
        i = self.posviews.index(posview)
        posview.disconnect(self.connections['posviews'].pop(i))
        del self.posviews[i]
        self.emit('changed', Change(['visualization', 'posviews', 'posview_height'], 'posview_removed', i))

    def remove_seqview(self, seqview):
        self.propvalues['seqview_width'] -= seqview.width_request
        i = self.seqviews.index(seqview)
        seqview.disconnect(self.connections['seqviews'].pop(i))
        del self.seqviews[i]
        self.emit('changed', Change(['visualization', 'seqviews', 'seqview_height'], 'seqview_removed', i))

    def add_msaviews(self, msaviews):
        if isinstance(msaviews, MSAView):
            msaviews = [msaviews]
        cb = self.handle_msaview_changed
        self.connections.setdefault('msaviews', []).extend(t.connect('changed', cb) for t in msaviews)
        if not self.msaviews:
            self.msaviews = []
        self.msaviews.extend(msaviews)
        self.emit('changed', Change(['visualization', 'msaviews'], 'msaviews_added', msaviews))
        
    def handle_msaview_changed(self, msaview, change):
        if change.has_changed('visualization'):
            self.emit('changed', Change('visualization', 'msaview_changed', [msaview, change]))

    def add_posviews(self, posviews):
        if isinstance(posviews, PosView):
            posviews = [posviews]
        self.propvalues['posview_height'] = self.posview_height + sum(t.height_request for t in posviews)
        cb = self.handle_posview_changed
        self.connections.setdefault('posviews', []).extend(t.connect('changed', cb) for t in posviews)
        if not self.posviews:
            self.posviews = []
        self.posviews.extend(posviews)
        self.emit('changed', Change(['visualization', 'posviews', 'posview_height'], 'posviews_added', posviews))

    def handle_posview_changed(self, posview, change):
        if change.has_changed('height_request'):
            self.posview_height = sum(t.height_request for t in self.posviews)
        if change.has_changed('visualization'):
            self.emit('changed', Change('visualization', 'posview_changed', [posview, change]))

    def add_seqviews(self, seqviews):
        if isinstance(seqviews, SeqView):
            seqviews = [seqviews]
        self.propvalues['seqview_width'] = self.seqview_width + sum(a.width_request for a in seqviews)
        cb = self.handle_seqview_changed
        self.connections.setdefault('seqviews', []).extend(a.connect('changed', cb) for a in seqviews)
        if not self.seqviews:
            self.seqviews = []
        self.seqviews.extend(seqviews)
        self.emit('changed', Change(['visualization', 'seqviews', 'seqview_width'], 'seqviews_added', seqviews))

    def handle_seqview_changed(self, seqview, change):
        if change.has_changed('width_request'):
            self.seqview_width = sum(a.width_request for a in self.seqviews)
        if change.has_changed('visualization'):
            self.emit('changed', Change('visualization', 'seqview_changed', [seqview, change]))
    
    def add(self, child, name=None):
        if child.msaview_classname == 'view.pos':
            self.add_posviews(child)
        elif child.msaview_classname == 'view.seq':
            self.add_seqviews(child)
        elif child.msaview_classname == 'view.msa':
            if self.msaviews:
                raise ValueError('only one MSAView is currently allowed.')
            self.add_msaviews(child)
        return Component.add(self, child, name)

    def integrate(self, ancestor, name=None):
        msa = ancestor.find_descendant('data.msa')
        if msa is None:
            msa = presets.get_preset('data.msa').component_class()
            if not msa.integrate(ancestor):
                raise TypeError('no suitable parent')
        self.msaview_name = msa.add(self, name)
        return self.msaview_name

    def zoom_to_msaview_area(self, msaview_area):
        self.hadjustment.page_size = msaview_area.width 
        self.vadjustment.page_size = msaview_area.height
        self.hadjustment.upper = msaview_area.total_width
        self.vadjustment.upper = msaview_area.total_height
        self.hadjustment.base_size = msaview_area.total_width
        self.vadjustment.base_size = msaview_area.total_height
        self.hadjustment.value = msaview_area.x 
        self.vadjustment.value = msaview_area.y
        
    def zoom_to_cell_size(self, x, y, show_all=False):
        msa = self.parent
        if not msa:
            raise ValueError('no msa')
        width = int(x * len(msa))
        height = int(y * len(msa.sequences))
        self.width = width + self.seqview_width
        self.height = height + self.posview_height
        if show_all:
            self.hadjustment.zoom_to_fit(width)
            self.vadjustment.zoom_to_fit(height)

    def zoom_to_fit(self):
        self.hadjustment.zoom_to_fit(self.hadjustment.page_size)
        self.vadjustment.zoom_to_fit(self.vadjustment.page_size)

    def get_detail_size(self):
        detail_sizes = (v.get_detail_size() for l in [self.posviews, self.seqviews, self.msaviews] for v in l)
        return [max(t) for t in zip(*detail_sizes) if t] or [0, 0]
            
    def zoom_to_details(self, fill=False):
        width, height = self.get_detail_size()
        if fill:
            width = max(width, self.hadjustment.page_size)
            height = max(height, self.vadjustment.page_size)
        self.hadjustment.zoom_to_size(width)
        self.vadjustment.zoom_to_size(height)
        
    def get_msaview_size_for_paper(self, page_setup=None):
        if page_setup is None:
            page_setup = gtk.PageSetup()
        w = page_setup.get_page_width(gtk.UNIT_POINTS) - self.seqview_width
        h = page_setup.get_page_height(gtk.UNIT_POINTS) - self.posview_height
        return (w, h)

    def get_msa_area(self):
        msa = self.parent
        if not (self.hadjustment.upper and self.vadjustment.upper):
            return [0, 0, len(msa), len(msa.sequences)]
        return [self.hadjustment.value/self.hadjustment.upper * len(msa),
                self.vadjustment.value/self.vadjustment.upper * len(msa.sequences),
                self.hadjustment.page_size/self.hadjustment.upper * len(msa),
                self.vadjustment.page_size/self.vadjustment.upper * len(msa.sequences)]

    def get_msaview_size_for_scale(self, scale=None, msa_area=None):
        msa = self.parent
        if not msa_area:
            msa_area = self.get_msa_area()
        if scale is None:
            detail_width, detail_height = self.get_detail_size()
            scale = (float(detail_width) / len(msa), float(detail_height) / len(msa.sequences))
        if isinstance(scale, (int, float)):
            scale = [scale, scale]
        elif len(scale) == 1:
            scale *= 2
        return (scale[0] * msa_area[2], scale[1] * msa_area[3])

    def get_msa_render_area_for_msaview_size(self, msaview_size, msa_area=None):
        if not msa_area:
            msa_area = self.get_msa_area()
        msa = self.parent
        x_scale = float(msaview_size[0]) / msa_area[2]
        y_scale = float(msaview_size[1]) / msa_area[3]
        x = msa_area[0] * x_scale
        y = msa_area[1] * y_scale
        width = msaview_size[0]
        height = msaview_size[1]
        total_width = len(msa) * x_scale
        total_height = len(msa.sequences) * y_scale
        return RenderArea(x, y, width, height, total_width, total_height)
        
    def get_msa_render_area_for_msa_area(self, msa_area):
        msaview_size = (self.hadjustment.page_size, self.vadjustment.page_size)
        return self.get_msa_render_area_for_msaview_size(msaview_size, msa_area)
        
    def draw_image(self, cr=None, msa_render_area=None):
        if msa_render_area is None:
            msa_render_area = RenderArea(0, 0, self.hadjustment.upper, self.vadjustment.upper, self.hadjustment.upper, self.vadjustment.upper)
        x = msa_render_area.x
        y = msa_render_area.y
        width = msa_render_area.width
        height = msa_render_area.height
        total_width = msa_render_area.total_width
        total_height = msa_render_area.total_height
        if cr is None:
            total_width = self.seqview_width + int(msa_render_area.width)
            total_height = self.posview_height + int(msa_render_area.height)
            image = cairo.ImageSurface(cairo.FORMAT_ARGB32, total_width, total_height)
            cr = pangocairo.CairoContext(cairo.Context(image))
        cr.save()
        for seqview in self.seqviews:
            cr.save()
            render_area = RenderArea(0, y, seqview.width_request, height, seqview.width_request, total_height)
            seqview.render(cr, render_area)
            cr.restore()
            cr.translate(seqview.width_request, 0)
        for msaview in self.msaviews:
            cr.save()
            msaview.render(cr, msa_render_area)
            cr.restore()
        cr.translate(0, height)
        for posview in self.posviews:
            cr.save()
            render_area = RenderArea(x, 0, width, posview.height_request, total_width, posview.height_request)
            posview.render(cr, render_area)
            cr.restore()
            cr.translate(0, posview.height_request)
        cr.restore()
        return cr

    def draw_image_with_heading(self, cr, msa_render_area, heading_layout, heading_height):
        """Convenience method for drawing to a preconfigured page."""
        cr.save()
        cr.move_to(0, 0)
        cr.set_source_rgb(0, 0, 0)
        cr.show_layout(heading_layout)
        cr.translate(0, 2 * heading_height)
        self.draw_image(cr, msa_render_area)
        cr.restore()

    def _prepare_page(self, cr, heading=None, page_area=None, background=None):
        if background:
            cr.set_source_rgba(*background.rgba)
            cr.paint()
        if page_area:
            cr.rectangle(*page_area)
            cr.clip()
            cr.translate(*page_area[:2])
        if heading:
            cr.set_source_rgb(0, 0, 0)
            cr.show_layout(heading)
            cr.translate(0, 2 * heading.get_line(0).get_pixel_extents()[1][3])
        
    def get_page_setup(self, msa_area=None, width=None, height=None, paper_size=None, landscape=False, margins=None, h_padding=0, v_padding=0):
        """Prepare a page setup for an image export.
        
        msa_area: the portion of the msa to show.
        width, height: paper size including margins and padding in points. 
            See convert_to_points() for other units. None means fit to paper_size
            and 'detail' means use a custom paper that is just big enough to show 
            msa_area in detail with margins and padding. 
        paper_size: default paper size.
        landscape: orientation of default paper.
        margins: paper margins, as for set_margins()
        h_padding, v_padding: required extra space (e.g. for headings and such).
          
        """
        page_setup = gtk.PageSetup()
        set_margins(page_setup, margins)
        if isinstance(paper_size, str):
            paper_size = parse_paper_name(paper_size)
        if paper_size is not None:
            page_setup.set_paper_size(paper_size)
        paper_size = page_setup.get_paper_size()
        if landscape:
            page_setup.set_orientation(gtk.PAGE_ORIENTATION_LANDSCAPE)
        else:
            page_setup.set_orientation(gtk.PAGE_ORIENTATION_PORTRAIT)
        if width is None and height is None:
            return page_setup
        if msa_area is None:
            msa_area = self.get_msa_area()
        detail_size = self.get_detail_size()
        if width is None:
            width = page_setup.get_paper_width(gtk.UNIT_POINTS)
        elif width == 'detail':
            width = math.ceil(detail_size[0] / len(self.parent) * msa_area[2] +
                              self.seqview_width +
                              page_setup.get_left_margin(gtk.UNIT_POINTS) +
                              page_setup.get_right_margin(gtk.UNIT_POINTS) +
                              h_padding)
        if height is None:
            height = page_setup.get_paper_height(gtk.UNIT_POINTS)
        elif height == 'detail':
            height = math.ceil(detail_size[1] / len(self.parent.sequences) * msa_area[3] +
                               self.posview_height +
                               page_setup.get_top_margin(gtk.UNIT_POINTS) +
                               page_setup.get_bottom_margin(gtk.UNIT_POINTS) +
                               v_padding)
        resulting_paper_size = gtk.paper_size_new_custom('custom', 'Custom', width, height, gtk.UNIT_POINTS)
        page_setup.set_paper_size(resulting_paper_size)
        page_setup.set_orientation(gtk.PAGE_ORIENTATION_PORTRAIT)
        return page_setup
    
    def get_heading(self, text=None, font=None):
        """Return a standard heading and its vertical size.
        
        text: None means use the path to the msa.
        font: A pango.FontDescription or a font description string. 
            None means use the font:heading_default preset. 
        """
        pc = pangocairo.cairo_font_map_get_default().create_context()
        if font is None:
            font = presets.get_value('font:heading_default')
        elif isinstance(font, str):
            font = pango.FontDescription(font)
        layout = pango.Layout(pc)
        layout.set_font_description(font)
        layout.set_text('Xj')
        if text is None:
            text = self.parent.path 
        layout.set_text(text)
        return layout
        
    def get_standard_page_setup(self, msa_area=None, width=None, height=None, paper_size=None, landscape=False, margins=None, heading=None):
        """Convenience function for .get_page_setup() with/without a heading."""
        v_padding = 0
        if heading:
            v_padding = 2 * heading.get_line(0).get_pixel_extents()[1][3]
        return self.get_page_setup(msa_area, width, height, paper_size, landscape, margins, 0, v_padding)
        
    def save_image(self, path, page_setup, msa_area=None, heading=None, format=None, background=None):
        """Save the current layout to an image file. Good for making figures.
        
        path: where to save the image.
        page_setup: image dimensions, for example from .get_standard_page_setup().
            For png images, the page_setup sizes in points will be taken as pixel sizes.   
        msa_area: the portion of the msa to show, as [position, sequence, columns, rows] 
            or None to save what's currently in view..
        heading: a pango.Layout() heading, for example from .get_heading().
        format: 'pdf', 'png', 'ps' or 'svg'. None means guess from path.
        background: image background color. None means white.

        Returns the cairo context for the resulting image. 
        """
        if format is None:
            format = os.path.splitext(path)[1][1:].lower()
        if msa_area is None:
            msa_area = self.get_msa_area()
        paper_width = page_setup.get_paper_width(gtk.UNIT_POINTS)
        paper_height = page_setup.get_paper_height(gtk.UNIT_POINTS)
        heading_height = 0
        if heading:
            heading_height = heading.get_line(0).get_pixel_extents()[1][3]
        if format == 'png':
            surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, int(paper_width), int(paper_height))
            #page_area = [int(page_setup.get_left_margin(gtk.UNIT_POINTS)),
            #             int(page_setup.get_top_margin(gtk.UNIT_POINTS)),
            #             int(paper_width) - int(page_setup.get_left_margin(gtk.UNIT_POINTS)) - int(page_setup.get_right_margin(gtk.UNIT_POINTS)),
            #             int(paper_height) - int(page_setup.get_top_margin(gtk.UNIT_POINTS)) - int(page_setup.get_bottom_margin(gtk.UNIT_POINTS))]
            page_area = [int(n) for n in get_page_area(page_setup)]
            if background is None:
                background = Color(1, 1, 1)
        else:
            vector_surfaces = {'pdf': cairo.PDFSurface, 'ps': cairo.PSSurface, 'svg': cairo.SVGSurface}
            surface = vector_surfaces[format](path, paper_width, paper_height)
            page_area = get_page_area(page_setup)
        cr = pangocairo.CairoContext(cairo.Context(surface))
        msaview_width = page_area[2] - self.seqview_width
        msaview_height = page_area[3] - self.posview_height - heading_height * 2
        msaview_size = [msaview_width, msaview_height]
        msa_render_area = self.get_msa_render_area_for_msaview_size(msaview_size, msa_area)
        self._prepare_page(cr, heading, page_area, background)
        self.draw_image(cr, msa_render_area)
        if format == 'png':
            surface.write_to_png(path)
        return cr
        
    def posterize_image(self, path, image_setup=None, msa_area=None, heading=None, crop_marks=False, format=None, background=None, document_setup=None, enumerate_pages=True):
        """Save the current layout to a printable document, split over multiple pages if necessary. 
        
        path: where to save the image.
        image_setup: image dimensions, for example from .get_standard_page_setup(). 
            None means use document_setup (yields a single page document). 
            Margins must be equal or greater than the margins in document_setup.
        msa_area: the portion of the msa to show, as [position, sequence, columns, rows] 
            or None to save what's currently in view.
        heading: a pango.Layout() heading, for example from .get_heading(). None 
            means use '[Unsaved MSA]'. Page enumeration details will be suffixed 
            to the heading text. 
        format: 'pdf', 'ps' or 'svg'. None means guess from path.
        background: image background color. None means white.
        document_setup: a gtk.PageSetup() or None for default paper and margins.
        
        Returns the cairo context for the resulting document. 
        """
        if document_setup is None:
            document_setup = gtk.PageSetup()
        if image_setup is None:
            image_setup = document_setup.copy()
        if msa_area is None:
            msa_area = self.get_msa_area()
        if format is None:
            format = os.path.splitext(path)[1][1:].lower()
        paper_width = document_setup.get_paper_width(gtk.UNIT_POINTS)
        paper_height = document_setup.get_paper_height(gtk.UNIT_POINTS)
        vector_surfaces = {'pdf': cairo.PDFSurface, 'ps': cairo.PSSurface, 'svg': cairo.SVGSurface}
        surface = vector_surfaces[format](path, paper_width, paper_height)
        cr = pangocairo.CairoContext(cairo.Context(surface))
        heading_height = 0
        heading_width = 0
        if heading:
            log_extents = heading.get_line(0).get_pixel_extents()[1]
            heading_width = log_extents[2]
            heading_height = log_extents[3] * 2
        page_enumeration = None
        page_enumeration_height = 0
        if enumerate_pages:
            pc = pangocairo.cairo_font_map_get_default().create_context()
            page_enumeration = pango.Layout(pc)
            page_enumeration.set_font_description(presets.get_value('font:default'))
            page_enumeration.set_text('Xj')
            page_enumeration_height = page_enumeration.get_line(0).get_pixel_extents()[1][3]
        page_area = get_page_area(document_setup)
        page_area[1] += page_enumeration_height
        page_area[3] -= page_enumeration_height
        image_area = get_page_area(image_setup)
        msaview_width = image_area[2] - self.seqview_width
        msaview_height = image_area[3] - self.posview_height - heading_height
        msaview_size = [msaview_width, msaview_height]
        msa_render_area = self.get_msa_render_area_for_msaview_size(msaview_size, msa_area)
        width_extents = WidthExtents.get_extents(self, msa_area, page_area, msa_render_area)
        height_extents = HeightExtents.get_extents(self, msa_area, page_area, msa_render_area, heading_height)
        msa_path = self.parent.path or '[Unsaved MSA]'
        def prepare_page(page_h, page_v):
            page_width_extents = width_extents[page_h]
            page_height_extents = height_extents[page_v]
            crop_mark_line_width = 0.5
            cr.set_source_rgb(0, 0, 0)
            if page_enumeration:
                cr.save()
                templ = "%(path)s, page %(page)s of %(pages)s ([%(page_h)s,%(page_v)s] / [%(h_pages)sx%(v_pages)s]), positions %(first_pos)s-%(last_pos)s, sequences %(first_seq)s-%(last_seq)s"
                first_pos = '*'
                last_pos = '*'
                first_seq = '*'
                last_seq = '*'
                if page_width_extents.position is not None:
                    first_pos = int(round(page_width_extents.position, 5)) + 1
                    last_pos = int(math.ceil(round(page_width_extents.position + page_width_extents.n_positions, 5))) 
                if page_height_extents.sequence is not None:
                    first_seq = int(round(page_height_extents.sequence, 5)) + 1
                    last_seq = int(math.ceil(round(page_height_extents.sequence + page_height_extents.n_sequences, 5))) 
                values = dict(path=msa_path,
                              page=page_v * len(width_extents) + page_h + 1,
                              pages=len(width_extents) * len(height_extents),
                              page_h=page_h + 1,
                              page_v=page_v + 1,
                              h_pages=len(width_extents),
                              v_pages=len(height_extents),
                              first_pos=first_pos,
                              last_pos=last_pos,
                              first_seq=first_seq,
                              last_seq=last_seq)
                page_enumeration.set_text(templ % values)
                cr.move_to(0, -page_enumeration_height - crop_mark_line_width)
                cr.show_layout(page_enumeration)
                cr.restore()
            if crop_marks:
                cr.save()
                cr.set_line_width(crop_mark_line_width)
                cr.rectangle(-0.5 * crop_mark_line_width, 
                             -0.5 * crop_mark_line_width, 
                             page_width_extents.page_width + crop_mark_line_width, 
                             page_height_extents.page_height + crop_mark_line_width)
                cr.stroke()
                cr.restore()
            cr.rectangle(0, 0, page_width_extents.page_width, page_height_extents.page_height)
            cr.clip()
        def draw_heading(page_h, page_v):
            x = width_extents[page_h].page_start_x
            y = height_extents[page_v].page_start_y
            if x >= heading_width or y >= heading_height or (height_extents[page_v].heading_y is None):
                return
            cr.save()
            cr.set_source_rgb(0, 0, 0)
            cr.translate(-x, -height_extents[page_v].heading_y)
            cr.show_layout(heading)
            cr.restore()
        def draw_seqviews(page_h, page_v):
            page_width_extents = width_extents[page_h]
            page_height_extents = height_extents[page_v]
            if not (page_width_extents.n_seqviews and page_height_extents.msaview_height):
                return
            cr.save()
            cr.translate(0, page_height_extents.heading_height or 0)
            x_offset = page_width_extents.seqview_start_x
            page_x = 0
            for seqview_index in range(page_width_extents.seqview_start, page_width_extents.seqview_start + page_width_extents.n_seqviews):
                seqview = self.seqviews[seqview_index]
                cr.save()
                x = x_offset
                y = page_height_extents.msaview_start_y
                width = min(page_width_extents.seqview_width - page_x, seqview.width_request - x_offset)
                height = page_height_extents.msaview_height
                area = RenderArea(x, y, width, height, seqview.width_request, msa_render_area.total_height)
                seqview.render(cr, area)
                cr.restore()
                x_offset = 0
                page_x += width
                cr.translate(width, 0)
            cr.restore()
        def draw_msaview(page_h, page_v):
            page_width_extents = width_extents[page_h]
            page_height_extents = height_extents[page_v]
            if not (page_width_extents.msaview_width and page_height_extents.msaview_height):
                return
            cr.save()
            cr.translate(page_width_extents.seqview_width or 0, page_height_extents.heading_height or 0)
            area = RenderArea(page_width_extents.msaview_start_x, 
                              page_height_extents.msaview_start_y, 
                              page_width_extents.msaview_width, 
                              page_height_extents.msaview_height, 
                              msa_render_area.total_width, 
                              msa_render_area.total_height)
            self.msaviews[0].render(cr, area)
            cr.restore()
        def draw_posviews(page_h, page_v):
            page_width_extents = width_extents[page_h]
            page_height_extents = height_extents[page_v]
            if not page_width_extents.msaview_width and page_height_extents.n_posviews:
                return
            y_offset = page_height_extents.posview_start_y
            page_y = 0
            cr.save()
            cr.translate(page_width_extents.seqview_width, (page_height_extents.heading_height or 0) + (page_height_extents.msaview_height or 0)) 
            for posview_index in range((page_height_extents.posview_start or 0), (page_height_extents.posview_start or 0) + page_height_extents.n_posviews):
                posview = self.posviews[posview_index]
                cr.save()
                x = page_width_extents.msaview_start_x
                y = y_offset
                width = page_width_extents.msaview_width
                height = min(page_height_extents.posview_height - page_y, posview.height_request - y_offset)
                area = RenderArea(x, y, width, height, msa_render_area.total_width, posview.height_request)
                posview.render(cr, area)
                cr.restore()
                y_offset = 0
                page_y += height
                cr.translate(0, height)
            cr.restore()
                
        cr.translate(page_area[0], page_area[1])
        if False:
            from pprint import pprint
            for i, page_width_extents in enumerate(width_extents):
                print '*** width extents page %s ***' % (i + 1)
                pprint(page_width_extents.__dict__)
                print
            for i, page_height_extents in enumerate(height_extents):
                print '*** height extents page %s ***' % (i + 1)
                pprint(page_height_extents.__dict__)
                print
        for page_v in range(len(height_extents)):
            for page_h in range(len(width_extents)):
                cr.save()
                prepare_page(page_h, page_v)
                draw_heading(page_h, page_v)
                draw_seqviews(page_h, page_v)
                draw_msaview(page_h, page_v)
                draw_posviews(page_h, page_v)
                cr.show_page()
                cr.restore()
        return cr

class MSAViewListSetting(SettingList):
    element_setting_type = MSAViewSetting
    tag = 'msaview'
    
class PosViewListSetting(SettingList):
    element_setting_type = PosViewSetting
    tag = 'posview'
    
class SeqViewListSetting(SettingList):
    element_setting_type = SeqViewSetting
    tag = 'seqview'
    
class LayoutSetting(ComponentSetting):
    component_class = Layout
    setting_types = dict(height=IntSetting,
                         msaviews=MSAViewListSetting,
                         posviews=PosViewListSetting,
                         #posview_height=IntSetting,
                         seqviews=SeqViewListSetting,
                         #seqview_width=IntSetting,
                         width=IntSetting)
    
presets.register_component_defaults(LayoutSetting)

s = LayoutSetting(dict(msaviews=MSAViewListSetting([presets.get_setting('view.msa:standard')]),
                       posviews=PosViewListSetting([presets.get_setting('view.pos:standard')]),
                       seqviews=SeqViewListSetting([presets.get_setting('view.seq:standard')])))
                       
presets.add_preset('layout:standard', s)

class ZoomToDetailsAction(Action):
    action_name = 'zoom-to-details'
    path = ['Zoom', 'Zoom to details']
    tooltip = 'Zoom in so that all details become visible.'

    @classmethod
    def applicable(cls, target=None, coord=None):
        if target.msaview_classname != 'layout' and not target.msaview_classname.startswith('view.'):
            return
        return cls(target, coord)

    def get_options(self):
        return [BooleanOption(propname='fill', default=True, value=True, nick='Fill view', tooltip='Expand image to fill the view if detail size is smaller than actual size.')]

    def run(self):
        self.target.zoom_to_details(self.params['fill'])
    
register_action(ZoomToDetailsAction)

class ZoomToScale(Action):
    action_name = 'zoom-to-scale'
    path = ['Zoom', 'Zoom to scale']
    tooltip = 'Zoom to a specific cell size.'

    @classmethod
    def applicable(cls, target=None, coord=None):
        if target.msaview_classname.startswith('view.'):
            try:
                target = target.parent
            except:
                return 
        if target.msaview_classname != 'layout':
            return
        return cls(target, coord)

    def get_options(self):
        return [IntOption(propname='x', default=5, value=5, minimum=0, maximum=1000, nick='X', tooltip='Horizontal letter size.'),
                IntOption(propname='y', default=10, value=10, minimum=0, maximum=1000, nick='Y', tooltip='Vertical letter size.'),
                BooleanOption(propname='show_all', default=False, value=False, nick='Show all', tooltip='Adjust image size to show the entire msa in the given scale.')]

    def run(self):
        self.target.zoom_to_cell_size(self.params['x'], self.params['y'], self.params['show_all'])
    
register_action(ZoomToScale)

class CenterAction(Action):
    action_name = 'center'
    path = ['Zoom', 'Center']
    tooltip = 'Center view on a particular spot in the MSA.'

    @classmethod
    def applicable(cls, target=None, coord=None):
        if target.msaview_classname == 'layout':
            if not target.msaviews:
                return
            target = target.msaviews[0]
        if target.msaview_classname != 'view.msa':
            return
        if not target.msa:
            return
        return cls(target, coord)

    def get_options(self):
        return [BoundaryOption(propname='position-start', value=None, default=None, nick='Start', tooltip='Index or motif start boundary in the range.'),
                BoundaryOption(propname='position-end', value=None, default=None, nick='End', tooltip='Index or motif for the end boundary in the range.'),
                BoundaryOption(propname='reference', value=None, default=None, nick='Reference', tooltip='Treat indexes/motifs relative to this sequence instead of the MSA.'),
                BoundaryOption(propname='sequence-start', value=None, default=None, nick='Sequence Start', tooltip='Index or ID for the first sequence in the range.'),
                BoundaryOption(propname='sequence-end', value=None, default=None, nick='Sequence End', tooltip='Index or ID for the last sequence in the range.'),
                BooleanOption(propname='regex', default=True, value=True, nick='Regular Expression', tooltip='Use regular expressions to match sequence identifiers.')]

    def set_options(self, options):
        Action.set_options(self, options)
        if self.params['position-start'] is None and self.params['sequence-start'] is None:
            raise ValueError('must set at least one of position-start or sequence-start')
    
    def run(self):
        if not self.target.hadjustment.page_size:
            self.target.hadjustment.page_size = 640
        if not self.target.vadjustment.page_size:
            self.target.vadjustment.page_size = 480
        if self.params['position-start']:
            positions = self.target.msa.get_position_region(self.params['position-start'], self.params['position-end'], self.params['reference'], self.params['regex'])
            xfocus = (positions.start + 0.5 * positions.length) / len(self.target.msa)
            x = int(xfocus * self.target.hadjustment.upper - 0.5 * self.target.hadjustment.page_size) 
            self.target.hadjustment.value = x
        if self.params['sequence-start']:
            sequences = self.target.msa.get_sequence_region(self.params['sequence-start'], self.params['sequence-end'], self.params['regex'])
            yfocus = (sequences.start + 0.5 * sequences.length) / len(self.target.msa.sequences)
            y = int(yfocus * self.target.vadjustment.upper - 0.5 * self.target.vadjustment.page_size)
            self.target.vadjustment.value = y

register_action(CenterAction)

class PanStepsAction(Action):
    action_name = 'pan-steps'
    path = ['Zoom', 'Pan steps']
    tooltip = 'Pan view a number of steps.'

    @classmethod
    def applicable(cls, target=None, coord=None):
        if target.msaview_classname == 'layout':
            if not target.msaviews:
                return
            target = target.msaviews[0]
        if not target.msaview_classname.startswith('view.'):
            return
        if not target.msa:
            return
        return cls(target, coord)

    def get_options(self):
        return [IntOption(propname='horizontal-steps', minimum=-10000, maximum=10000, default=0, value=0, nick='Horizontal steps', tooltip="Number of steps to pan to the right (negative to pan left)."),
                IntOption(propname='vertical-steps', minimum=-10000, maximum=10000, default=0, value=0, nick='Vertical steps', tooltip="Number of steps to pan down (negative to pan up).")]

    def run(self):
        if self.params['horizontal-steps']:
            self.target.hadjustment.scroll_step(self.params['horizontal-steps'])
        if self.params['vertical-steps']:
            self.target.vadjustment.scroll_step(self.params['vertical-steps'])
    
register_action(PanStepsAction)

def parse_sizes(size_def, unitless=False):
    unit = None
    if not unitless and size_def[-2:].isalpha():
        s = size_def[-2:].lower()
        try:
            unit = units[s]
        except KeyError:
            raise ValueError('%r is not one of the recognized length units (%s)', (s, ', '.join(units)))
        size_def = size_def[:-2] 
    words = size_def.split('x')
    return [float(s) for s in words], unit

class PaperOption(Option):
    def __init__(self, component=None, propname=None, default=_UNSET, value=_UNSET, nick=None, tooltip=None, allow_fit=False):
        Option.__init__(self, component, propname, default, value, nick, tooltip)
        self.allow_fit = allow_fit
        
    def parse_str(self, string):
        string = string.strip().lower()
        if string == 'default':
            return string
        if self.allow_fit and (not string or string == 'fit'):
            return string
        if not string or string == 'fit':
            return string
        if parse_paper_name(string) is None:
            raise ValueError('not a valid paper name')
        return string

    @classmethod
    def get_paper_size(cls, string):
        if string == 'default':
            return gtk.PaperSize()
        if not string or string == 'fit':
            return None
        return parse_paper_name(string)
        
class LengthOption(Option):
    def __init__(self, component=None, propname=None, default=_UNSET, value=_UNSET, nick=None, tooltip=None, allow_fit=False):
        Option.__init__(self, component, propname, default, value, nick, tooltip)
        self.allow_fit = allow_fit
        
    def parse_str(self, string):
        string = string.strip().lower()
        if string == 'detail':
            return string
        if self.allow_fit and (not string or string == 'fit'):
            return string
        sizes, unit = parse_sizes(string)
        if len(sizes) != 1:
            raise ValueError("cannot parse %r to a valid size" % string)
        return string
    
    @classmethod
    def get_length(cls, string, default_unit=default_unit):
        if string == 'detail':
            return string
        if not string or (string == 'fit'):
            return None
        (size,), unit = parse_sizes(string)
        return convert_to_points(size, unit or default_unit) 
    
class MarginsOption(Option):
    def parse_str(self, string):
        string = string.strip().lower()
        if string == 'default':
            return string
        sizes, unit = parse_sizes(string)
        if len(sizes) not in [1, 2, 4]:
            raise ValueError("must be set as M[unit], VxH[unit] or TxBxLxR[unit] or 'default'")
        return string

    @classmethod
    def get_margins(cls, string, default_unit=default_unit):
        if string == 'default':
            return None
        sizes, unit = parse_sizes(string)
        return [convert_to_points(size, unit or default_unit) for size in sizes] 
        
class ExportImage(Action):
    action_name = 'export-image'
    path = ['Export', 'Image']
    tooltip = 'Save the current layout to an image file, good for making figures.'
    
    @classmethod
    def applicable(cls, target, coord=None):
        if target.msaview_classname != 'layout':
            return
        return cls(target, coord)
    
    def get_options(self):
        path = self.target.parent.path + '.pdf' if self.target else ''
        return [Option(None, 'path', path, path, 'Path', 'Where to save the image.'),
                LengthOption(None, 'width', '', '', 'Width', "Image width as W[unit], 'fit' (or leave empty) to fit to page, or 'detail' for just big enough to show all details. The default unit is mm. Use points (pt) to set exact pixel sizes for png images.", allow_fit=True),
                LengthOption(None, 'height', '', '', 'Height', "Image height as H[unit], 'fit' (or leave empty) to fit to page or 'detail' for just big enough to show all details. The default unit is mm. Use points (pt) to set exact pixel sizes for png images.", allow_fit=True),
                PaperOption(None, 'paper-size', 'default', 'default', 'Paper size', "Canvas size for the exported image as 'default', 'fit' (or leave unset) or a valid paper name. png images take their pixel sizes from paper sizes in points.", allow_fit=True),
                BooleanOption(None, 'landscape', False, False, 'Landscape', 'Use landscape orientation for paper size.'),
                MarginsOption(None, 'margins', 'default', 'default', 'Margins', "Page margins as M[unit], HxV[unit], LxRxTxB[unit] or 'default'. The default unit is mm."),
                Option(None, 'format', '', '', 'Format', 'File type of the exported image; pdf, png, ps or svg, or leave unset to guess from filename.'),
                BooleanOption(None, 'heading', True, True, 'Heading', 'Include an image heading.'),
                Option(None, 'heading-text', '', '', 'Heading text', 'Text for the heading, or leave unset to use the msa path.'),
                FontOption(None, 'heading-font', presets.get_value('font:heading_default'), presets.get_value('font:heading_default'), 'Heading font', 'Font for the heading.'),
                ColorOption(None, 'background-color', presets.get_value('color:white'), presets.get_value('color:white'), 'Background color', 'Background color for the image'),
                ]

    def set_options(self, options):
        Action.set_options(self, options)
        if not self.params['format']:
            try:
                self.params['format'] = os.path.splitext(self.params['path'])[1][1:].lower()
            except:
                raise ValueError('format not set, and cannot guess from filename extension')
        supported_formats = ('pdf', 'png', 'ps', 'svg')
        if self.params['format'] not in supported_formats:
            raise ValueError('%r is not among the supported formats %s' % (self.params['format'], supported_formats))
        self.params['heading-layout'] = None
        if self.params['heading']:
            self.params['heading-layout'] = self.target.get_heading(self.params['heading-text'].strip() or None, self.params['heading-font'])
        self.params['msa-area'] = self.target.get_msa_area()
        if self.params['format'] != 'png' and self.params['background-color'] == presets.get_value('color:white'):
            self.params['background-color'] = None
        width = LengthOption.get_length(self.params['width'])
        height = LengthOption.get_length(self.params['height'])
        margins = MarginsOption.get_margins(self.params['margins'])
        paper_size = PaperOption.get_paper_size(self.params['paper-size'])
        self.params['page-setup'] = self.target.get_standard_page_setup(self.params['msa-area'], width, height, paper_size, self.params['landscape'], margins, self.params['heading-layout'])
             
    def run(self):
        self.target.get_compute_manager().compute_all()
        self.target.save_image(self.params['path'], self.params['page-setup'], self.params['msa-area'], self.params['heading-layout'], self.params['format'], self.params['background-color'])

register_action(ExportImage)
        
class ExportPosterizedImage(Action):
    action_name = 'export-posterized-image'
    path = ['Export', 'Posterized image']
    tooltip = 'Save the current layout to a printable document, split over multiple pages if necessary.'
    
    @classmethod
    def applicable(cls, target, coord=None):
        if target.msaview_classname != 'layout':
            return
        return cls(target, coord)
    
    def get_options(self):
        path = self.target.parent.path + '.pdf' if self.target else ''
        return [Option(None, 'path', path, path, 'Path', 'Where to save the image.'),
                LengthOption(None, 'width', 'detail', 'detail', 'Width', "Image width as W[unit], or 'detail' (or leave empty) for just big enough to show all details. The default unit is mm."),
                LengthOption(None, 'height', 'detail', 'detail', 'Height', "Image height as H[unit], or 'detail' (or leave empty) for just big enough to show all details. The default unit is mm."),
                PaperOption(None, 'image-paper-size', 'default', 'default', 'Paper size', "Canvas size for the exported image as 'default', 'fit' (or leave unset) to use document paper size or a valid paper name."),
                BooleanOption(None, 'image-landscape', False, False, 'Landscape', 'Use landscape orientation for image paper size.'),
                MarginsOption(None, 'image-margins', 'default', 'default', 'Margins', "Image margins as M[unit], HxV[unit], LxRxTxB[unit] or 'default'. Should be equal or greater than the document page margins. The default unit is mm."),
                PaperOption(None, 'document-paper-size', 'default', 'default', 'Paper size', "Paper size for the individual exported pages as 'default' or a valid paper name."),
                BooleanOption(None, 'document-landscape', False, False, 'Landscape', 'Use landscape orientation for paper size.'),
                MarginsOption(None, 'document-margins', 'default', 'default', 'Margins', "Page margins as M[unit], HxV[unit], LxRxTxB[unit] or 'default'. The default unit is mm."),
                BooleanOption(None, 'enumerate-pages', True, True, 'Enumerate pages', 'Add page enumeration information to each page.'),
                BooleanOption(None, 'crop-marks', True, True, 'Crop marks', 'Add crop marks to each page.'),
                Option(None, 'format', '', '', 'Format', 'File type of the exported image; pdf, png, ps or svg, or leave unset to guess from filename.'),
                BooleanOption(None, 'heading', True, True, 'Heading', 'Include an image heading.'),
                Option(None, 'heading-text', '', '', 'Heading text', 'Text for the heading, or leave unset to use the msa path.'),
                FontOption(None, 'heading-font', presets.get_value('font:heading_default'), presets.get_value('font:heading_default'), 'Heading font', 'Font for the heading.'),
                ColorOption(None, 'background-color', presets.get_value('color:white'), presets.get_value('color:white'), 'Background color', 'Background color for the image'),
                ]

    def set_options(self, options):
        Action.set_options(self, options)
        self.params['heading-layout'] = None
        if self.params['heading']:
                self.params['heading-layout'] = self.target.get_heading(self.params['heading-text'].strip() or None, self.params['heading-font'])
        self.params['msa-area'] = self.target.get_msa_area()
        if not self.params['format']:
            try:
                self.params['format'] = os.path.splitext(self.params['path'])[1][1:].lower()
            except:
                raise ValueError('format not set, and cannot guess from filename extension')
        supported_formats = ('pdf', 'ps', 'svg')
        if self.params['format'] not in supported_formats:
            raise ValueError('%r is not among the supported multipage formats %s' % (self.params['format'], supported_formats))
        document_margins = MarginsOption.get_margins(self.params['document-margins'])
        document_paper_size = gtk.PaperSize()
        if self.params['document-paper-size']:
            document_paper_size = PaperOption.get_paper_size(self.params['document-paper-size'])
            if document_paper_size is None:
                raise ValueError('invalid paper name %r' % self.params['document-paper-size'])
        
        if self.params['background-color'] == presets.get_value('color:white'):
            self.params['background-color'] = None
        width = LengthOption.get_length(self.params['width'])
        height = LengthOption.get_length(self.params['height'])
        image_margins = MarginsOption.get_margins(self.params['image-margins'])
        image_paper_size = PaperOption.get_paper_size(self.params['image-paper-size']) or document_paper_size
        self.params['image-setup'] = self.target.get_standard_page_setup(self.params['msa-area'], width, height, image_paper_size, self.params['image-landscape'], image_margins, self.params['heading-layout'])
        self.params['document-setup'] = self.target.get_standard_page_setup(paper_size=document_paper_size, landscape=self.params['document-landscape'], margins=document_margins)
        
    def run(self):
        self.target.get_compute_manager().compute_all()
        self.target.posterize_image(self.params['path'], 
                                    self.params['image-setup'], 
                                    self.params['msa-area'], 
                                    self.params['heading-layout'], 
                                    self.params['crop-marks'], 
                                    self.params['format'], 
                                    self.params['background-color'], 
                                    self.params['document-setup'],
                                    self.params['enumerate-pages'])

register_action(ExportPosterizedImage)
