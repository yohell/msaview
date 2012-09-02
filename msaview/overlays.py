import math
import time

import cairo
import gobject
import gtk
import pango
import pangocairo

from adjustments import ZoomAdjustment
from color import Color
from cache import Cache
from component import (Change, 
                       Connection, 
                       prop)
from preset import (BoolSetting,
                    ComponentSetting,
                    FloatSetting,
                    FontSetting,
                    IntSetting,
                    presets)
from options import (BooleanOption, 
                     FloatOption, 
                     FontOption, 
                     IntOption)
from plotting import (chequers, 
                      stripes,
                      tick_labels,
                      tick_lines,
                      vector_based)
from renderers import (RenderArea, 
                       Renderer, 
                       get_ticks,
                       integrate_ancestor_msa)
from selection import (Area, 
                       Selection)

class Overlay(Renderer):
    __gproperties__ = dict(
        view = (
            gobject.TYPE_PYOBJECT,
            'view',
            'the view containing the overlay',
            gobject.PARAM_READWRITE))
    
    view = prop('view')

    def _draw(self, cr, area, view_area):
        "Called by .render() and .draw() to do the actual drawing."
            
    def render(self, cr, view_area=None):
        "Static rendering of full view."    
        if view_area is None:
            view_area = self.view._get_view_area()
        area = gtk.gdk.Rectangle(0, 0, view_area.width, view_area.height)
        self._draw(cr, area, view_area)

    def draw(self, cr, area):
        "Dynamic rendering, possibly of partial views"
        view_area = self.view._get_view_area()
        self._draw(cr, area, view_area)
    
    def prepare_update(self):
        pass
    
    def integrate(self, ancestor, name=None):
        type = self.msaview_classname.split('.')[1]
        viewtype = 'view'
        if type in ('msa', 'pos', 'seq'):
            viewtype += '.' + type 
        view = ancestor.find_descendant(lambda c: c.msaview_classname.startswith(viewtype))
        if view is None:
            try:
                view_preset = presets.get_preset(viewtype)
            except:
                view_preset = presets.get_preset(viewtype + '.msa')
            view = view_preset.component_class()
            if not view.integrate(ancestor):
                raise TypeError('no suitable parent')
        self.view = view
        self.msaview_name = view.add(self, name)
        return self.msaview_name

class Miniature(object):
    def __init__(self, renderer, width, height):
        self.renderer = renderer
        self.width = width
        self.height = height
    
    def __hash__(self):
        return hash((self.__class__, self.renderer, self.width, self.height))
    
    def __eq__(self, other):
        return (isinstance(other, self.__class__) and
                other.renderer == self.renderer and
                other.width == self.width and
                other.height == self.height) 
            
class Locator(Overlay):
    __gproperties__ = dict(
        always_show = (gobject.TYPE_BOOLEAN,
            'always show',
            'dynamic show/hide behavior',
            False,
            gobject.PARAM_READWRITE),
        timeout = (gobject.TYPE_FLOAT,
            'timeout',
            'seconds from draw to hide for the locator',
            0,
            1e10,
            0.5,
            gobject.PARAM_READWRITE),
        width = (gobject.TYPE_FLOAT,
            'width',
            'horizontal proportion of the view occupied by the locator',
            0,
            1.0,
            0.2,
            gobject.PARAM_READWRITE),
        height = (gobject.TYPE_FLOAT,
            'height',
            'vertical proportion of the view occupied by the locator',     
            0,
            1.0,
            0.2,
            gobject.PARAM_READWRITE),
        max_width = (gobject.TYPE_INT,
            'max width',
            'maximum absolute horizontal size of the locator',
            0,
            100000,
            100,
            gobject.PARAM_READWRITE),
        max_height = (gobject.TYPE_INT,
            'max height',
            'maximum absolute vertical size of the locator',     
            0,
            100000,
            100,
            gobject.PARAM_READWRITE))

    msaview_classname = 'overlay.locator'
        
    propdefaults = dict(alpha=1.0,
                        always_show=False,
                        height=0.2,
                        max_height=100,
                        max_width=100,
                        timeout=0.5,
                        width=0.2)
    
    def __init__(self):
        Overlay.__init__(self)
        self.cache = Cache()
        self._last_navigate = None
        
    always_show = prop('always_show')
    timeout = prop('timeout')
    width = prop('width')
    height = prop('height')
    max_width = prop('max_width')
    max_height = prop('max_height')

    def __eq__(self, other):
        if other is self:
            return True
        return (isinstance(other, self.__class__) and
                (other.alpha == self.alpha and
                 other.always_show == self.always_show and
                 other.timeout == self.timeout and
                 other.height == self.height and
                 other.max_height == self.max_height and
                 other.max_width == self.max_width and
                 other.width == self.width and
                 other.view == self.view))
        
    def do_set_property_view(self, pspec, view):
        for name in ['hadjustment', 'vadjustment']:
            try:
                self.connections.pop(name).disconnect()
            except KeyError:
                pass
            if view is not None:
                adj = getattr(view, name)
                id = adj.connect('value-changed', self.handle_adjustment_change)
                self.connections[name] = Connection(adj, id)
        self.propvalues['view'] = view
        self.emit('changed', Change())
        
    def handle_adjustment_change(self, adjustment=None):
        self._last_navigate = time.time()
    
    def _get_area(self, area=None, view_area=None):
        if view_area is None:
            view_area = self.view._get_view_area()
        width = min(int(self.width * view_area.width), self.max_width)
        height = min(int(self.height * view_area.height), self.max_height)
        x = int(view_area.width) - width
        if area and (min(width, height) < 5 or
            area.y >= height or 
            area.x + area.width < x):
            return None
        return gtk.gdk.Rectangle(x, 0, width, height)
        
    def _get_miniature(self, renderer_stack, width, height):
        miniature = Miniature(renderer_stack, width, height)
        image = self.cache.get(miniature, None)
        if image is None:
            image = cairo.ImageSurface(cairo.FORMAT_ARGB32, int(width), int(height))
            cr = gtk.gdk.CairoContext(cairo.Context(image))
            render_area = RenderArea(0, 0, width, height, width, height)
            cr.set_source_rgb(1, 1, 1)
            cr.paint()
            for renderer in renderer_stack.renderers:
                if renderer.get_slow_render(render_area):
                    break
                cr.save()
                renderer.render(cr, render_area)
                cr.restore()
            self.cache[miniature] = image
        return image
        
    def _draw(self, cr, area, view_area):
        locator_area = self._get_area(area, view_area)
        if locator_area is None:
            return
        locator_x, _, locator_width, locator_height = locator_area
        # Frame
        cr.rectangle(*area)
        cr.clip()
        cr.translate(locator_x, 0)
        cr.set_source_rgba(.6, .6, .6, self.alpha)
        line_width = 1.0
        if vector_based(cr):
            line_width = 0.5
            cr.set_source_rgba(0, 0, 0, self.alpha)
        cr.rectangle(0.5 * line_width, 0.5 * line_width, locator_width - line_width, locator_height - line_width)
        cr.set_line_width(line_width)
        cr.stroke()
        # Miniature
        width = locator_width - 2 * line_width
        height = locator_height - 2 * line_width
        image = self._get_miniature(self.view.renderers, width, height)
        cr.save()
        cr.rectangle(line_width, line_width, width, height)
        cr.clip()
        # A bug in cairo misaligns the paint_with_alpha origin vertically with vector backends. 
        if vector_based(cr):
            cr.set_source_surface(image, line_width, 1)
        else:
            cr.set_source_surface(image, line_width, line_width)
        cr.paint_with_alpha(self.alpha)
        cr.restore()
        # View outline
        vx_first = int(float(view_area.x) / view_area.total_width * width)
        vx_last = int(math.ceil(float(view_area.x + view_area.width) / view_area.total_width * width))
        vx_last = min(vx_last, width)
        v_width = vx_last - vx_first + 1
        vy_first = int(float(view_area.y) / view_area.total_height * height)
        vy_last = int(math.ceil(float(view_area.y + view_area.height) / view_area.total_height * height))
        vy_last = min(vy_last, height)
        v_height = vy_last - vy_first + 1
        cr.rectangle(vx_first + 0.5 * line_width, vy_first + 0.5 * line_width, v_width - line_width, v_height - line_width)
        cr.set_source_rgba(1, 0, 0, self.alpha)
        cr.stroke()

    def render(self, cr, view_area=None):
        if not self.always_show:
            return
        if view_area is None:
            view_area = self.view._get_view_area()
        area = gtk.gdk.Rectangle(0, 0, view_area.width, view_area.height)
        self._draw(cr, area, view_area)
        
    def prepare_update(self):
        if self.always_show or self._last_navigate is None:
            return
        if time.time() - self._last_navigate > self.timeout:
            self._last_navigate = None
            return [self._get_area()]
    
    def draw(self, cr, area):
        view_area = self.view._get_view_area()
        if not view_area:
            return
        if self.always_show or self._last_navigate is not None:
            self._draw(cr, area, view_area)

    def get_options(self):
        return [FloatOption(self, 'alpha', hint_step=0.05, hint_digits=2),
                BooleanOption(self, 'always_show'),
                FloatOption(self, 'timeout', hint_digits=2, hint_maximum=4),
                FloatOption(self, 'width', hint_digits=2),
                FloatOption(self, 'height', hint_digits=2),
                IntOption(self, 'max_width', hint_maximum=300),
                IntOption(self, 'max_height', hint_maximum=300)]

class LocatorSetting(ComponentSetting):
    component_class = Locator
    setting_types = dict(alpha=FloatSetting,
                         always_show=BoolSetting,
                         height=FloatSetting,
                         max_height=IntSetting,
                         max_width=IntSetting,
                         timeout=FloatSetting,
                         width=FloatSetting)
    
presets.register_component_defaults(LocatorSetting)

# TODO: Selection appearance settings.

class SelectionOverlay(Overlay):
    __gproperties__ = dict(
        area_dash = (
            gobject.TYPE_PYOBJECT,
            'area dash',
            'edge dash for area selections',
            gobject.PARAM_READWRITE),
        area_fill = (
            gobject.TYPE_PYOBJECT,
            'area fill',
            'background fill for area selections',
            gobject.PARAM_READWRITE),
        position_dash = (
            gobject.TYPE_PYOBJECT,
            'position dash',
            'edge dash for position selections',
            gobject.PARAM_READWRITE),
        position_fill = (
            gobject.TYPE_PYOBJECT,
            'position fill',
            'background fill for position selections',
            gobject.PARAM_READWRITE),
        selection = (
            gobject.TYPE_PYOBJECT,
            'selection',
            'the selection to display',
            gobject.PARAM_READWRITE),
        sequence_dash = (
            gobject.TYPE_PYOBJECT,
            'sequence dash',
            'edge dash for sequence selections',
            gobject.PARAM_READWRITE),
        sequence_fill = (
            gobject.TYPE_PYOBJECT,
            'sequence fill',
            'background fill for sequence selections',
            gobject.PARAM_READWRITE),
        update_interval = (
            gobject.TYPE_FLOAT,
            'update interval',
            'minimum time between edge dash updates (time between marching ant steps)',
            0.1,
            10,
            0.5,
            gobject.PARAM_READWRITE))
    
    msaview_classname = 'overlay.selection'
    
    propdefaults = {}
    
    def __init__(self):
        Overlay.__init__(self)
        self._last_dash_update = time.time()
        self.propvalues.update(
            area_dash=[3, 3],
            #area_fill=lines((0, 0, .3, 0.3), (0, 0, .3, 0.1), 2),
            area_fill=chequers((0, 0, .3, 0.3), (0, 0, .3, 0.1), 1),
            position_dash=[5, 5],
            position_fill=stripes((.3, 0, 0, 0.3), (.3, 0, 0, 0.1), 2, 3),
            sequence_dash=[5, 5],
            sequence_fill=stripes((0, .2, 0, 0.3), (0, .2, 0, 0.1), 2, 3, True))

    area_dash = prop('area_dash')
    area_fill = prop('area_fill')
    position_dash = prop('position_dash')
    position_fill = prop('position_fill')
    selection = prop('selection')
    sequence_dash = prop('sequence_dash')
    sequence_fill = prop('sequence_fill')
    update_interval = prop('update_interval')

    def __eq__(self, other):
        if other is self:
            return True
        return (isinstance(other, self.__class__) and
                (other.alpha == self.alpha and
                 other.area_dash == self.area_dash and
                 other.area_fill == self.area_fill and
                 other.position_dash == self.position_dash and
                 other.selection == self.selection and
                 other.sequence_dash == self.sequence_dash and
                 other.sequence_fill == self.sequence_fill and
                 other.update_interval == self.update_interval and
                 other.view == self.view))
        
        
    def _get_dash_offset(self, dash):
        return -1 * (int(time.time() / self.update_interval) % sum(dash)) + 0.5
        
    def do_set_property_selection(self, pspec, selection):
        if selection != self.selection:
            self.propvalues['selection'] = selection
            self.update_change_handlers(selection=selection)
            self.handle_selection_change(self.selection, Change())

    def handle_selection_change(self, selection, changes):
        self.emit('changed', Change('visualization'))

    def _msa_coordinates(self, value, page_size, upper, msa_size):
        first = int(float(value) / upper * msa_size)
        last = int(float(value + page_size) / upper * msa_size)
        last = min(last, msa_size - 1)
        return first, last - first + 1
    
    def _pixel_coordinates(self, view_size, msa_size, region):
        first = int(float(view_size) / msa_size * region.start)
        last = int(float(view_size) / msa_size * (region.start + region.length))
        return first, last - first
    
    def _get_area_rectangles(self, areas, msa_width, msa_height, view_area, msa_in_view, area):
        rectangles = []
        for a in self.selection.areas.areas:
            if not msa_in_view.overlap(a):
                continue
            x, width = self._pixel_coordinates(view_area.total_width, msa_width, a.positions)
            y, height = self._pixel_coordinates(view_area.total_height, msa_height, a.sequences)
            rectangles.append([int(x - view_area.x), int(y - view_area.y), width, height])
        return rectangles
    
    def _get_region_rectangles(self, regions, msa_size, primary_value, primary_total_size, visible_region, other_value, other_total_size, other_offset, other_size, sequence_rectangles=False):
        rectangles = []
        _first = max(0, int(other_value) + other_offset - 1)
        _size = int(min(other_total_size, int(other_value) + other_offset + other_size + 1) - _first)
        _first -= int(other_value)
        # This extends region selection rectangles past view borders on 
        # off sides, which makes selections in neighboring views look good:
        _first -= 1
        _size += 2
        for region in regions:
            if not visible_region.overlap(region):
                continue
            offset, size = self._pixel_coordinates(primary_total_size, msa_size, region)
            if sequence_rectangles:
                rectangles.append([_first, int(offset - primary_value), _size, size])
            else:
                rectangles.append([int(offset - primary_value), _first, size, _size])
        return rectangles
    
    def _get_rectangles(self, area, view_area):
        if not self.selection.msa:
            return [], [], []
        msa_width = len(self.selection.msa)
        msa_height = len(self.selection.msa.sequences)
        if not (view_area.total_height and view_area.total_height and msa_width and msa_height):
            return [], [], [] 
        pos, n_pos = self._msa_coordinates(view_area.x + area.x, area.width, view_area.total_width, msa_width)
        seq, n_seq = self._msa_coordinates(view_area.y + area.y, area.height, view_area.total_height, msa_height)
        msa_in_area = Area.from_rect(pos, seq, n_pos, n_seq)
        # Rectangles:
        sel = self.selection
        mp = msa_in_area.positions
        ms = msa_in_area.sequences
        rects = self._get_region_rectangles
        a_rects = []
        p_rects = []
        s_rects = []
        if isinstance(self.view.hadjustment, ZoomAdjustment):
            if isinstance(self.view.vadjustment, ZoomAdjustment):
                a_rects = self._get_area_rectangles(sel.areas, msa_width, msa_height, view_area, msa_in_area, area)
            p_rects = rects(sel.positions.regions, msa_width, view_area.x, view_area.total_width, mp, view_area.y, view_area.total_height, area.y, area.height)
        if isinstance(self.view.vadjustment, ZoomAdjustment):
            s_rects = rects(sel.sequences.regions, msa_height, view_area.y, view_area.total_height, ms, view_area.x, view_area.total_width, area.x, area.width, True)
        return a_rects, p_rects, s_rects
    
    def _draw_dash(self, cr, rectangles, dash, offset, colors=None):
        if colors == None:
            colors = ((0, 0, 0), (1, 1, 1))
        line_width = 1.0
        if vector_based(cr):
            line_width = 0.5
        for r in rectangles:
            x, y, w, h = r
            cr.rectangle(x + 0.5 * line_width, y + 0.5 * line_width, w - line_width, h - line_width)
        cr.set_dash([])
        cr.set_source_rgb(*colors[0])
        cr.set_line_width(line_width)
        cr.stroke_preserve()
        cr.set_source_rgb(*colors[1])
        cr.set_dash(dash, offset)
        cr.stroke()

    def _draw(self, cr, area, view_area, dash_offset=None):
        if not self.selection or not self.view:
            return
        areas, positions, sequences = self._get_rectangles(area, view_area)
        if not (areas or positions or sequences):
            return
        cr.rectangle(*area)
        cr.clip()
        # Backgrounds
        cr.set_source(self.area_fill)
        for r in areas:
            cr.rectangle(*r)
        cr.fill()
        cr.set_source(self.position_fill)
        for r in positions:
            cr.rectangle(*r)
        cr.fill()
        cr.set_source(self.sequence_fill)
        for r in sequences:
            cr.rectangle(*r)
        cr.fill()
        # Dashes
        area_dash_offset = dash_offset
        position_dash_offset = dash_offset
        sequence_dash_offset = dash_offset
        if dash_offset is None:
            area_dash_offset = self._get_dash_offset(self.area_dash)
            position_dash_offset = self._get_dash_offset(self.position_dash)
            sequence_dash_offset = self._get_dash_offset(self.position_dash)
        self._draw_dash(cr, areas, self.area_dash, area_dash_offset, ((0, 0, 0), (1, 1, 0)))
        self._draw_dash(cr, positions, self.position_dash, position_dash_offset)
        self._draw_dash(cr, sequences, self.sequence_dash, sequence_dash_offset)
        
    def render(self, cr, view_area=None):
        if view_area is None:
            view_area = self.view._get_view_area()
        area = gtk.gdk.Rectangle(0, 0, view_area.width, view_area.height)
        self._draw(cr, area, view_area, dash_offset=0.5)

    def draw(self, cr, area):
        view_area = self.view._get_view_area()
        if view_area is None:
            return
        self._draw(cr, area, view_area)

    def prepare_update(self):
        t = time.time()
        if t <= self._last_dash_update + self.update_interval:
            return
        self._last_dash_update = t
        w = int(self.view.hadjustment.page_size)
        h = int(self.view.vadjustment.page_size)
        return sum(self._get_rectangles(gtk.gdk.Rectangle(0, 0, w, h), self.view._get_view_area()), [])
    
    def get_options(self):
        return []

    def integrate(self, ancestor, name=None):
        self.msaview_name = Overlay.integrate(self, ancestor, name)
        msa = integrate_ancestor_msa(self, ancestor)
        self.selection = msa.selection
        return self.msaview_name 

class SelectionSetting(ComponentSetting):
    component_class = SelectionOverlay
    
presets.register_component_defaults(SelectionSetting)

presets.add_preset('font:ruler_default', presets.get_setting('font:default'))

class Ruler(Overlay):
    __gproperties__ = dict(
        font = (
            gobject.TYPE_PYOBJECT,
            'font',
            'font for numbers on ruler',
            gobject.PARAM_READWRITE),
        msa = (
            gobject.TYPE_PYOBJECT,
            'msa',
            'the msa to measure',
            gobject.PARAM_READWRITE))
    
    propdefaults = dict(alpha=1.0,
                        font=presets.get_setting('font:ruler_default'))
    font = prop('font')
    
    def __init__(self):
        Overlay.__init__(self)
        self.pango_context = pangocairo.cairo_font_map_get_default().create_context()
    
    def do_set_property(self, pspec, value):
        if pspec.name in ('font', 'msa'):
            if value != getattr(self, pspec.name):
                self.propvalues[pspec.name] = value
            if pspec.name == 'msa':
                self.update_change_handlers(msa=value)
                self.handle_msa_change(value, Change())
            else:
                self.emit('changed', Change('visualization'))
            return
        Overlay.do_set_property(self, pspec, value)
    
    def handle_msa_change(self, msa, change):
        if change.has_changed('sequences'):
            self.emit('changed', Change('visualization'))
        
    def _draw(self, cr, offset, length, total_length, area_x, area_width, view_height, total_items):
        """Call only from subclasses (that conform to .render() signature).
        
        cr is exprected to be properly clipped, translated (and rotated) before
        this method is called.
        
        """
        start = float(offset) / total_length * total_items
        items_in_view = min(float(total_items), float(length) / total_length * total_items)
        item_size = float(total_length) / total_items
        first_tick, tick_stop, tick_step = get_ticks(start, items_in_view)
        ticks = range(first_tick, total_items, tick_step)
        tick_height = 10
        cr.translate(int(-offset), 0)
        tick_lines(cr, Color(.5, .5, .5), self.alpha, tick_height, ticks, item_size, offset + area_x, area_width)
        if tick_step > 2 and not (tick_step % 2):
            minor_ticks = range(first_tick - int(0.5 * tick_step), tick_stop, tick_step)
            tick_lines(cr, Color(.5, .5, .5), self.alpha, tick_height - 2, minor_ticks, item_size, offset + area_x, area_width)
        if item_size > 2:
            tick_lines(cr, Color(.5, .5, .5), self.alpha, 2, range(total_items), item_size, offset + area_x, area_width)
        layout = pango.Layout(self.pango_context)
        layout.set_font_description(self.font)
        layout.set_text('X')
        # The intricate return values from ...get_pixel_extents():
        #ink, logic = layout.get_line(0).get_pixel_extents()
        #ink_xbearing, ink_ybearing, ink_w, ink_h = ink
        #log_xbearing, log_ybearing, log_w, log_h = logic
        label_height = layout.get_line(0).get_pixel_extents()[1][3]
        cr.translate(0, 2)
        tick_labels(cr, layout, Color(0, 0, 0), self.alpha, ticks, item_size, offset + area_x, area_width)

    def draw(self, cr, area):
        view_area = self.view._get_view_area()
        if view_area is None:
            return
        self._draw(cr, area, view_area)
        
    def get_options(self):
        return Overlay.get_options(self) + [FontOption(self)]
    
    def integrate(self, ancestor, name=None):
        self.msaview_name = Overlay.integrate(self, ancestor, name)
        self.msa = integrate_ancestor_msa(self, ancestor)
        return self.msaview_name 

class PosRuler(Ruler):
    msaview_classname = 'overlay.pos.ruler'
    def _draw(self, cr, area, view_area):
        if view_area is None:
            view_area = self.view._get_view_area()
        if not self.msa:
            return
        area = gtk.gdk.Rectangle(0, 0, view_area.width, view_area.height)
        cr.rectangle(*area)
        cr.clip()
        Ruler._draw(self, cr, view_area.x, view_area.width, view_area.total_width, area.x, area.width, view_area.height, len(self.msa))
        
class PosRulerSetting(ComponentSetting):
    component_class = PosRuler
    setting_types = dict(alpha=FloatSetting,
                         font=FontSetting)

presets.register_component_defaults(PosRulerSetting)

class SeqRuler(Ruler):
    msaview_classname = 'overlay.seq.ruler'
    def _draw(self, cr, area, view_area):
        if view_area is None:
            view_area = self.view._get_view_area()
        if not self.msa:
            return
        area = gtk.gdk.Rectangle(0, 0, view_area.width, view_area.height)
        cr.rectangle(*area)
        cr.clip()
        cr.translate(self.view.hadjustment.page_size, 0)
        cr.rotate(math.pi / 2)
        Ruler._draw(self, cr, view_area.y, view_area.height, view_area.total_height, area.y, area.height, view_area.width, len(self.msa.sequences))
        
class SeqRulerSetting(ComponentSetting):
    component_class = SeqRuler
    setting_types = dict(alpha=FloatSetting,
                         font=FontSetting)

presets.register_component_defaults(SeqRulerSetting)

