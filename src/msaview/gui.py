import math
import os
import re
import sys
import traceback

import cairo
import gobject
import gtk
import pangocairo

from adjustments import ZoomAdjustment
from component import (Component,
                       Root)
from action import Coordinate
from cache import Cache
from preset import (ComponentSetting,
                    USER_PRESET_FILE,
                    presets,
                    save_to_preset_file,
                    save_to_user_preset_file,
                    remove_from_user_preset_file)
import msa
from options import (BooleanOption,
                     Option, 
                     SimpleOptionConfigDialog, 
                     make_options_context_menu)
from overlays import SelectionOverlay
from renderers import RenderArea
from selection import Region
from visualization import (Layout,
                           PosView, 
                           SeqView,
                           View)


class FragmentInfo(object):
    def __init__(self, renderer, render_area):
        self.renderer = renderer
        self.render_area = render_area
        
    def __hash__(self):
        return hash((FragmentInfo, self.renderer, self.render_area))
    
    def __eq__(self, other):
        return (isinstance(other, self.__class__) and
                other.renderer == self.renderer and 
                other.render_area == self.render_area)

class PartialDrawManager(gobject.GObject):
    __gsignals__ = dict(
        fragment_updated = (
            gobject.SIGNAL_RUN_FIRST,
            gobject.TYPE_NONE,
            (gobject.TYPE_INT, ) * 6))
    
    def __init__(self, cache, pool=None):
        gobject.GObject.__init__(self)
        self.cache = cache
        if pool is None:
            pool = []
        self.pool = pool
        self._idle_worker_id = None
        
    def add_job(self, fragment_info, renderer_index):
        if (fragment_info, renderer_index) in self.pool:
            return
        if not self._idle_worker_id:
            self._idle_worker_id = gobject.idle_add(self.process_job)
        self.pool.append((fragment_info, renderer_index))
        
    def draw_partial(self, cr, fragment_info, renderer_index=None):
        render_area = fragment_info.render_area
        try:
            renderers = fragment_info.renderer.renderers
        except:
            fragment_info.renderer.render(cr, render_area)
            return
        slow_job_done = False
        for i in range(renderer_index or 0, len(renderers)):
            r = renderers[i]
            if r.get_slow_render(render_area):
                if slow_job_done or renderer_index is None:
                    self.add_job(fragment_info, i)
                    return
                slow_job_done = True
            cr.save()
            r.render(cr, render_area)
            cr.restore()
            
    def process_job(self):
        fragment_info = None 
        fragment_priority = None
        renderer_index = None
        job_index = None
        i = 0
        while i < len(self.pool):
            frag, ri = self.pool[i]
            try:
                prio = self.cache.index(frag)
            except KeyError:
                del self.pool[i]
                continue
            if fragment_priority is None or prio < fragment_priority:
                fragment_priority = prio
                fragment_info = frag
                renderer_index = ri
                job_index = i
            i += 1
        if fragment_info is None:
            self._idle_worker_id = None
            return
        self.pool.pop(job_index)
        surface = self.cache.peek(fragment_info)
        cr = gtk.gdk.CairoContext(cairo.Context(surface))
        self.draw_partial(cr, fragment_info, renderer_index)
        a = fragment_info.render_area
        self.emit('fragment-updated', a.x, a.y, a.width, a.height, a.total_width, a.total_height)
        return True
        
    def flush_jobs(self):
        gobject.source_remove(self._idle_worker_id)
        self._idle_worker_id = None
        self.pool = {}

class ActionParamsDialog(gtk.Dialog):
    def __init__(self, action, window):
        title = action.nick or ' '.join(action.action_name.split('-'))
        dialog_options = gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT
        action_buttons = (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL, gtk.STOCK_OK, gtk.RESPONSE_OK) 
        gtk.Dialog.__init__(self, title, window, dialog_options, action_buttons)
        self.set_default_response(gtk.RESPONSE_OK)
        self.msaview_action = action
        self.config_widgets = []
        self.msaview_action_options = action.get_options()
        self.config_table = gtk.Table(len(self.msaview_action_options), 2)
        self.config_table.props.column_spacing = 5
        self.config_table.props.row_spacing = 2
        self.vbox.pack_start(self.config_table)
        for row, option in enumerate(self.msaview_action_options):
            if not isinstance(option, BooleanOption):
                label = gtk.Label()
                label.set_text(option.nick)
                label.set_tooltip_text(option.tooltip)
                label.props.xalign = 1.0
                self.config_table.attach(label, 0, 1, row, row + 1, xoptions=gtk.FILL)
            config = option.create_config_widget()
            self.config_table.attach(config, 1, 2, row, row + 1)
            self.config_widgets.append(config)
            config.connect('changed', self.on_config_widget_changed)
        self.on_config_widget_changed(None)
        self.show_all()
        
    def on_config_widget_changed(self, entry):
        self.set_response_sensitive(-5, False not in (w.valid for w in self.config_widgets))
        
def run_error_dialog(parent_window, label_text, detail_text):
    if False:
        print "Printing debug traceback from gui run error dialog function!"
        traceback.print_exc()
    if not str(detail_text):
        detail_text = "<no error message given>"
    dialog_options = gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT
    action_buttons = (gtk.STOCK_OK, gtk.RESPONSE_OK) 
    error = gtk.Dialog("Error", parent_window, dialog_options, action_buttons)
    reason = gtk.Label('%s:\n %s' % (label_text, detail_text))
    error.vbox.pack_start(reason)
    tb = traceback.format_exc()
    if tb:
        text = gtk.TextView()
        text.props.buffer.props.text = tb
        text.props.editable = False
        def print_error_on_double_middle_press(textview, event):
            if event.button == 2 and event.type == gtk.gdk._2BUTTON_PRESS:
                print >> sys.stderr, textview.props.buffer.props.text
        text.connect('button-press-event', print_error_on_double_middle_press)
        scroll = gtk.ScrolledWindow()
        scroll.add(text)
        expander = gtk.Expander('Traceback')
        expander.add(scroll)
        error.vbox.pack_start(expander)
    error.show_all()
    error.run()
    error.destroy()
    
def run_action_params_dialog(dialog):
    while True:
        if dialog.run() != gtk.RESPONSE_OK:
            return
        try:
            dialog.msaview_action.set_options(dialog.msaview_action_options)
            break
        except Exception, e:
            if False:
                print "Printing debug traceback from gui run_action_params_dialog set_options!"
                import traceback
                traceback.print_exc()
            dialog.hide()
            run_error_dialog(dialog.get_parent(), 'Error', e)
            dialog.show_all()
            continue
    return gtk.RESPONSE_OK
            
def run_action(action, window, error_label_text='Error'):
    if not action.get_options():
        action.set_options([])
        try:
            action.run()
        except Exception, e:
            if False:
                print "Printing debug traceback from gui run_action function!"
                import traceback
                traceback.print_exc()
            run_error_dialog(window, error_label_text, e)
        return
    dialog = ActionParamsDialog(action, window)
    while True:
        if run_action_params_dialog(dialog) == gtk.RESPONSE_OK:
            try:
                dialog.msaview_action.run()
            except Exception, e:
                if False:
                    print "Printing debug traceback from gui run action dialog!"
                    import traceback
                    traceback.print_exc()
                dialog.hide()
                run_error_dialog(dialog.get_parent(), error_label_text, e)
                dialog.show_all()
                continue
        dialog.destroy()
        return

def populate_action_popup_menu(window, menu_root, actions):
    def add_to_menu(menu, action, path):
        name = path[0]
        item = None
        for it in menu.get_children():
            if name == it.get_data('name'):
                item = it
        if len(path) == 1:
            if item:
                #if (not item.get_data('action') or item.get_data('action') == action): 
                #    print "name collision for action name", action.path, name   
                return
            menuitem = gtk.MenuItem(name)
            menuitem.set_data('name', name)
            menuitem.set_data('action', action)
            menuitem.connect('activate', lambda w: run_action(action, window))
            menuitem.set_tooltip_text(action.tooltip or '')
            menu.add(menuitem)
            return
        if item:
            if item.get_data('action'):
                #print "name collision for action name", item.get_data('action'), action.path, name
                return
            submenu = item.get_submenu()
        else:
            item = gtk.MenuItem(name)
            item.set_data('name', name)
            menu.add(item)
            submenu = gtk.Menu()
            item.set_submenu(submenu)
        add_to_menu(submenu, action, path[1:])
    for a in actions:
        add_to_menu(menu_root, a, a.path)

class ClickDrag(object):
    def __init__(self, x, y):        
        self.x = x
        self.y = y
        
class SelectionMetadata(object):
    type = ''
    def __init__(self, selection=None):
        self.selection = selection
    
class AreaSelectionMetadata(SelectionMetadata):
    type = 'area'
    def __init__(self, selection=None, area=None, origin=None, lock_positions=False, lock_sequences=False):
        self.selection = selection
        self.area = area
        self.origin = origin
        self.lock_positions = lock_positions
        self.lock_sequences = lock_sequences
        
class RegionSelectionMetadata(SelectionMetadata):
    type = 'region'
    def __init__(self, selection=None, regions=None, region=None, origin=None, axis=0):
        self.selection = selection
        self.regions = regions
        self.region = region
        self.origin = origin
        self.axis = axis
        
class RegionSelectionCreationMetadata(RegionSelectionMetadata):
    type = 'region-new'
    def __init__(self, selection=None, regions=None, region=None, origin=None, axis=None, base_axis_one=None):
        self.selection = selection
        self.regions = regions
        self.region = region
        self.origin = origin
        self.axis = axis
        self.base_axis_one = base_axis_one
    
        
class ZoomView(gtk.DrawingArea):
    __gsignals__ = {'button-press-event': 'override',
                    'button-release-event': 'override',
                    'expose-event': 'override',
                    'motion-notify-event': 'override',
                    'scroll-event': 'override'}
    fragment_size = 500
    def __init__(self, view=None):
        super(ZoomView, self).__init__()
        self.add_events(gtk.gdk.BUTTON_PRESS_MASK | 
                        gtk.gdk.BUTTON_RELEASE_MASK |
                        gtk.gdk.KEY_PRESS_MASK |
                        gtk.gdk.KEY_RELEASE_MASK |
                        gtk.gdk.POINTER_MOTION_MASK | 
                        gtk.gdk.LEAVE_NOTIFY_MASK | 
                        gtk.gdk.SCROLL_MASK)
        self._selection_snap_distance = 10
        self._region_selection_direction_threshold = 5
        self._selecting = None
        self.connections = dict(adjustments = [None, None])
        self._adjustments = [None, None]
        self._view = None
        if not isinstance(view, (PosView, SeqView)):
            self.set_property('can-focus', True)
        self.view = view
        self.cache = Cache()
        self._clickdrag = {2: None}
        self.partial_renderer = PartialDrawManager(self.cache)
        def draw_updates(partial_renderer, x, y, width, height, total_width, total_height):
            def crop_to_view(value, size, total, adj):
                if (total != adj.upper or 
                    value > adj.value + adj.page_size or 
                    value + size < adj.value):
                    return 0, 0
                end = min(value + size, adj.value + adj.page_size)
                value = max(value, adj.value)
                return int(value - adj.value), int(math.ceil(end - value))
            x, width = crop_to_view(x, width, total_width, self.view.hadjustment)
            y, height = crop_to_view(y, height, total_height, self.view.vadjustment)
            if width and height:
                self.draw(gtk.gdk.Rectangle(x, y, width, height))
        self.partial_renderer.connect('fragment-updated', draw_updates)
        self._check_updates = None
    
    def set_view(self, view):
        if self._view is not None:
            self._view.disconnect(self.connections['view'])
        self._view = view
        if view is None:
            self.connections['adjustments'] = [None, None]
        else:
            self.connections['view'] = view.connect('changed', self.handle_view_change)
            self._connect_adjustment(view.hadjustment, 0)
            self._connect_adjustment(view.vadjustment, 1)
    
    view = property(lambda s: s._view, set_view)
    
    def _connect_adjustment(self, adj, axis):
        if self._adjustments[axis] is not None:
            self._adjustments[axis].disconnect(self.connections['adjustments'][axis])
        self._adjustments[axis] = adj
        if isinstance(adj, ZoomAdjustment):
            self.connections['adjustments'][axis] = adj.connect('value-changed', lambda a: self.queue_draw())
            page_size = self.get_allocation()[2 + axis]
            adj.set_page_size(page_size)
        else:
            def handle_adj_value_change(adj):
                if adj.page_size != self.get_size_request()[axis]:
                    req = [-1, -1]
                    req[axis] = int(adj.page_size)
                    self.set_size_request(*req)
                else:
                    self.queue_draw()
            self.connections['adjustments'][axis] = adj.connect('value-changed', handle_adj_value_change)
        
    def handle_view_change(self, view, change):
        if change.has_changed('hadjustment'):
                self._connect_adjustment(view.hadjustment, 0)
        if change.has_changed('vadjustment'):
            self._connect_adjustment(view.vadjustment, 1)
        self.queue_draw()
                
    def do_size_allocate(self, allocation):
        gtk.DrawingArea.do_size_allocate(self, allocation)
        if isinstance(self.view.hadjustment, ZoomAdjustment):
            self.view.hadjustment.set_page_size(allocation.width)
        if isinstance(self.view.vadjustment, ZoomAdjustment):
            self.view.vadjustment.set_page_size(allocation.height)
    
    def _get_fragment(self, render_area):
        fragment_info = FragmentInfo(self.view.renderers, render_area)
        try:
            return self.cache[fragment_info]
        except:
            frag = cairo.ImageSurface(cairo.FORMAT_ARGB32, render_area.width, render_area.height)
            self.cache[FragmentInfo(self.view.renderers, render_area)] = frag
            cr = pangocairo.CairoContext(cairo.Context(frag))
            if self.view.background:
                cr.set_source_rgba(*self.view.background.rgba)
                cr.paint()
            self.partial_renderer.draw_partial(cr, fragment_info)
            return frag 
    
    def draw_renderers(self, cr, area):
        render_area = RenderArea.from_view_area(self.view, area)
        if not (render_area.width and render_area.height):
            return 
        cr.translate(area.x, area.y)
        cr.rectangle(0, 0, render_area.width, render_area.height)
        cr.clip()
        cr.translate(-(render_area.x % self.fragment_size), -(render_area.y % self.fragment_size))
        h_first = render_area.x / self.fragment_size
        v_first = render_area.y / self.fragment_size
        h_last = (render_area.x + render_area.width) / self.fragment_size
        v_last = (render_area.y + render_area.height) / self.fragment_size
        # Drawing right to left, bottom up because the slow renderers stack 
        # is, well, a stack. It processes last viewed fragment first. This will
        # appear to the user as I'm actually drawing left to right, top down.
        for v in range(v_last - v_first, -1, -1):
            y = (v + v_first) * self.fragment_size
            for h in range(h_last - h_first, -1, -1):
                x = (h + h_first) * self.fragment_size
                fw = min(self.fragment_size, render_area.total_width - x)
                fh = min(self.fragment_size, render_area.total_height - y)
                a = RenderArea(x, y, fw, fh, render_area.total_width, render_area.total_height)
                frag = self._get_fragment(a)
                cr.set_source_surface(frag, h * self.fragment_size, v * self.fragment_size)
                cr.rectangle(h * self.fragment_size, v * self.fragment_size, fw, fh)
                cr.fill()

    def draw_overlays(self, cr, area):
        for overlay in self.view.overlays:
            cr.save()
            overlay.draw(cr, area)
            cr.restore()
            
    def draw(self, area=None):
        if area is None:
            area = gtk.gdk.Rectangle(0, 0, self.view.hadjustment.page_size, self.view.vadjustment.page_size)
        cr = self.window.cairo_create()
        cr.save()
        self.draw_renderers(cr, area)
        cr.restore()
        self.draw_overlays(cr, area)
        
        
    def do_expose_event(self, event):
        if not self.view.renderers and not self.view.overlays:
            return
        if not (self.view.hadjustment.base_size or self.view.vadjustment.base_size):
            self.zoom_to_fit()
        if self._check_updates is None:
            self._check_updates = gobject.timeout_add(100, self.check_updates)
        self.draw(event.area)
        
    def check_updates(self):
        for overlay in self.view.overlays:
            areas = overlay.prepare_update() or []
            for area in areas:
                self.queue_draw_area(*area)
        return True
                
    def do_scroll_event(self, event):
        if event.state & gtk.gdk.SHIFT_MASK:
            try:
                i = [gtk.gdk.SCROLL_UP, gtk.gdk.SCROLL_DOWN].index(event.direction)
                event.direction = [gtk.gdk.SCROLL_LEFT, gtk.gdk.SCROLL_RIGHT][i]
            except:
                pass
        axis = 0 if event.direction in [gtk.gdk.SCROLL_LEFT, gtk.gdk.SCROLL_RIGHT] else 1
        amount = 1 if event.direction in [gtk.gdk.SCROLL_DOWN, gtk.gdk.SCROLL_RIGHT] else -1
        adj = self._adjustments[axis]
        if not isinstance(adj, ZoomAdjustment):
            return
        if event.state & gtk.gdk.CONTROL_MASK:
            xfocus = event.x / self._adjustments[0].page_size
            yfocus = event.y / self._adjustments[1].page_size
            if self.view.msaview_classname == 'view.msa':
                self.view.zoom_step(-amount, xfocus, yfocus)
            elif self.view.msaview_classname == 'view.pos':
                self.view.zoom_step(-amount, xfocus)
            elif self.view.msaview_classname == 'view.seq':
                self.view.zoom_step(-amount, yfocus)
        else:
            adj.scroll_step(amount)
        if self._clickdrag[2]:
            self._clickdrag[2] = ClickDrag(self.view.hadjustment.value + event.x, self.view.vadjustment.value + event.y)
        
    def zoom_to_fit(self):
        alloc = list(self.get_allocation())
        layout = self.view.find_ancestor('layout')
        if layout:
            layout.zoom_to_fit()
        else:
            self.view.zoom_to_fit()
        
    def get_detail_size(self):
        alloc = self.get_allocation()
        layout = self.view.find_ancestor('layout')
        if layout:
            detail = layout.get_detail_size()
        else:
            detail = self.view.renderers.get_detail_size()
        return [max(t) for t in zip((alloc.width, alloc.height), detail)]
        
    def zoom_to_details(self, xoffset=None, yoffset=None, detail=None):
        alloc = self.get_allocation()
        if not detail:
            detail = self.get_detail_size()
        layout = self.view.find_ancestor('layout')
        if layout:
            layout.hadjustment.zoom_to_size(detail[0], xoffset)
            layout.vadjustment.zoom_to_size(detail[1], yoffset)
        else:
            for adj, size, offset in zip(self._adjustments, detail, [xoffset, yoffset]):
                if isinstance(adj, ZoomAdjustment):
                    adj.zoom_to_size(size, offset)
    
    def _get_selection_overlay(self):
        for overlay in self.view.overlays:
            if isinstance(overlay, SelectionOverlay):
                return overlay
        return None
    
    def _get_msa_coordinates(self, x, y, msa):
        def bound(value, cap):
            return max(0, min(value, cap - 1))
        pos = int(x / self.view.hadjustment.upper * len(msa)) 
        seq = int(y / self.view.vadjustment.upper * len(msa.sequences))
        return bound(pos, len(msa)), bound(seq, len(msa.sequences))

    def _get_event_pixel_coordinates(self, event):
        x = self.view.hadjustment.value + event.x 
        y = self.view.vadjustment.value + event.y
        return x, y

    def _get_event_msa_coordinates(self, event, msa):
        x, y = self._get_event_pixel_coordinates(event)
        return self._get_msa_coordinates(x, y, msa)
        
    def do_button1_double_press_event(self, event):
        self._selecting = None
        sel = self._get_selection_overlay()
        if sel is None or sel.selection is None:
            return
        selection = sel.selection
        msa = selection.msa
        pos, seq = self._get_event_msa_coordinates(event, msa)
        shift = event.state & gtk.gdk.SHIFT_MASK
        control = event.state & gtk.gdk.CONTROL_MASK
        def rm_part(parts, *coord):
            get_part = getattr(parts, 'get_area', None) or getattr(parts, 'get_region')
            part = get_part(*coord)
            if part:
                parts.remove(part)
                return True
        if control:
            if rm_part(selection.areas, pos, seq):
                return
        removal_priority = [(selection.positions, pos), (selection.sequences, seq)]
        if shift:
            removal_priority.reverse()
        for regions, coord in removal_priority:
            if rm_part(regions, coord):
                return
        rm_part(selection.areas, pos, seq)

    def _snap_selection_edge(self, region, msa_size, upper, coord):
        snap = self._selection_snap_distance
        stop = float(region.start + region.length) / msa_size * upper
        if stop - snap <= coord < stop:
            return region.start
        start = float(region.start) / msa_size * upper
        if start <= coord < start + snap:
            return region.start + region.length - 1
        return None

    def _select_area(self, selection, hadj, pos, x, vadj, seq, y):
        msa = selection.msa
        area = selection.areas.get_area(pos, seq)
        if area:
            snap = self._snap_selection_edge
            origin_pos = snap(area.positions, len(msa), hadj.upper, x)
            origin_seq = snap(area.sequences, len(msa.sequences), vadj.upper, y)
            if origin_pos is None and origin_seq is None:
                return
            origin = (origin_pos, origin_seq)
            m = AreaSelectionMetadata(selection, area, origin, origin_pos is None, origin_seq is None)
        else:
            area = selection.areas.add_area(pos, seq, 1, 1)
            m = AreaSelectionMetadata(selection, area, (pos, seq))
        self._selecting = m

    def _modify_region_selection(self, selection, axis, regions, upper, coord, msa_size, msa_coord):
        region = regions.get_region(msa_coord)
        if region:
            origin = self._snap_selection_edge(region, msa_size, upper, coord)
            if origin is None:
                return
            return RegionSelectionMetadata(selection, regions, region, origin, axis)

    def do_button1_single_press_event(self, event):
        sel = self._get_selection_overlay()
        # the user is only allowed to select stuff if there's a selection to affect and a way of showing it. 
        if sel is None or sel.selection is None:
            return
        selection = sel.selection
        msa = selection.msa
        x, y = self._get_event_pixel_coordinates(event)
        pos, seq = self._get_msa_coordinates(x, y, msa)
        shift = event.state & gtk.gdk.SHIFT_MASK
        control = event.state & gtk.gdk.CONTROL_MASK
        hadj = self.view.hadjustment
        vadj = self.view.vadjustment
        if control: 
            # Control selects areas only if both axes are zoomable. 
            if False not in (isinstance(adj, ZoomAdjustment) for adj in self._adjustments):
                self._select_area(selection, hadj, pos, x, vadj, seq, y)
                return
        region_select_params = [(selection, 0, selection.positions, hadj.upper, x, len(msa), pos),
                                (selection, 1, selection.sequences, vadj.upper, y, len(msa.sequences), seq)]
        if shift:
            region_select_params.reverse()
        for params in region_select_params:
            m = self._modify_region_selection(*params)
            if m:
                self._selecting = m
                return 
        rel_x = x / hadj.upper
        rel_y = y / vadj.upper
        m = RegionSelectionCreationMetadata(selection, origin=(rel_x, rel_y))
        self._selecting = m

    def do_button1_press_event(self, event):
        if event.type == gtk.gdk._3BUTTON_PRESS:
            pass
        elif event.type == gtk.gdk._2BUTTON_PRESS:
            self.do_button1_double_press_event(event)
        else:
            self.do_button1_single_press_event(event)
        
    def do_button2_press_event(self, event):
        if event.type == gtk.gdk._2BUTTON_PRESS:
            alloc = self.get_allocation()
            detail = self.get_detail_size()
            if (self.view.hadjustment.upper < alloc.width or 
                self.view.vadjustment.upper < alloc.height):
                self.zoom_to_fit()
            elif ((isinstance(self.view.hadjustment, ZoomAdjustment) and self.view.hadjustment.upper < detail[0]) or 
                  (isinstance(self.view.vadjustment, ZoomAdjustment) and self.view.vadjustment.upper < detail[1])):
                self.zoom_to_details(event.x, event.y)
            else:
                self.zoom_to_fit()
        self._clickdrag[2] = ClickDrag(self.view.hadjustment.value + event.x, self.view.vadjustment.value + event.y)
        
    def do_button2_release_event(self, event):
        self._clickdrag[2] = None
        
    def do_button3_press_event(self, event):
        pos = None
        seq = None
        x = self.view.hadjustment.value + event.x
        y = self.view.vadjustment.value + event.y
        if self.view.msa:
            if isinstance(self.view.hadjustment, ZoomAdjustment):
                pos = int(x / self.view.hadjustment.upper * len(self.view.msa))
            if isinstance(self.view.vadjustment, ZoomAdjustment):
                seq = int(y / self.view.vadjustment.upper * len(self.view.msa.sequences))
        coord = Coordinate(pos, seq, x, y, self.view.hadjustment.upper, self.view.vadjustment.upper)
        menu = gtk.Menu()
        w = self.parent
        while not isinstance(w, gtk.Window):
            w = w.parent
        msa = self.view.msa
        actions = msa.get_actions(coord)
        actions.extend(self.view.get_actions(coord))
        actions.extend(self.view.parent.get_actions(coord))
        for r in self.view.renderers.renderers:
            actions.extend(r.get_actions(coord))
        actions.sort(key=lambda a: a.path)
        populate_action_popup_menu(w, menu, actions)
        view_options_menu = make_options_context_menu(self.view)
        if view_options_menu.get_children():
            options_menu = gtk.Menu()
            options_root = gtk.MenuItem('Options')
            options_root.set_submenu(options_menu)
            menu.append(options_root)
            view_options_root = gtk.MenuItem(self.view.__class__.__name__)
            view_options_root.set_submenu(view_options_menu)
            options_menu.append(view_options_root)
        if not menu.get_children():
            na = gtk.MenuItem('- not available -')
            na.set_sensitive(False)
            menu.append(na)
        menu.show_all()
        menu.popup(None, None, None, event.button, event.time)
        
    def do_button_press_event(self, event):
        handler = getattr(self, 'do_button%d_press_event' % event.button, None)
        if handler:
            return handler(event)
        
    def do_button_release_event(self, event):
        if event.button == 1:
            if self._selecting and getattr(self._selecting, 'regions', None):
                self._selecting.regions.incorporate(self._selecting.region)
            self._selecting = None
            return
        elif event.button == 2:
            return self.do_button2_release_event(event)

    def _update_selection_from_motion_event(self, event):
        meta = self._selecting
        selection = meta.selection
        msa = selection.msa
        x, y = self._get_event_pixel_coordinates(event)
        msa_coords = self._get_msa_coordinates(x, y, msa)
        pos, seq = msa_coords
        def region_stats(msa_coord, origin):
            start = min(msa_coord, origin)
            length = max(msa_coord, origin) - start + 1
            return start, length
        if meta.type == 'area':
            pos_start = meta.area.positions.start
            pos_length = meta.area.positions.length
            seq_start = meta.area.sequences.start
            seq_length = meta.area.sequences.length
            if not meta.lock_positions:
                pos_start, pos_length = region_stats(pos, meta.origin[0])
            if not meta.lock_sequences:
                seq_start, seq_length = region_stats(seq, meta.origin[1])
            meta.selection.areas.update_area(meta.area, pos_start, seq_start, pos_length, seq_length)
        elif meta.type == 'region':
            msa_coord = msa_coords[meta.axis]
            start, length = region_stats(msa_coord, meta.origin)
            meta.regions.update_region(meta.region, start, length)
        elif meta.type == 'region-new':
            shift = bool(event.state & gtk.gdk.SHIFT_MASK)
            if meta.base_axis_one is None:
                origin_x = int(meta.origin[0] * self.view.hadjustment.upper)
                origin_y = int(meta.origin[1] * self.view.vadjustment.upper)
                deltax = abs(x - origin_x)
                deltay = abs(y - origin_y)
                t = self._region_selection_direction_threshold
                def zoomable_axis(i):
                    return isinstance(self._adjustments[i], ZoomAdjustment)
                # lti: temporary list variable of (distance, axis) items. 
                lti = [(d, i) for i, d in enumerate([deltax, deltay]) if zoomable_axis(i)]
                lti.sort()
                if not lti:
                    return
                if lti[-1][0] < self._region_selection_direction_threshold:
                    return
                if len(lti) == 2:
                    base_axis_one = lti[-1][-1] == 1 
                    axis = lti[0 if shift else 1][1]
                else:
                    axis = lti[0][1]
                    base_axis_one = axis == 1
                meta.base_axis_one = base_axis_one
                meta.axis = axis
                meta.origin = self._get_msa_coordinates(origin_x, origin_y, msa)
            axis = 1 if meta.base_axis_one ^ shift else 0
            if axis != meta.axis and meta.region is not None and isinstance(self._adjustments[axis], ZoomAdjustment):
                meta.regions.remove(meta.region)
                meta.region = None
                meta.regions = None
                meta.axis = axis
            start, length = region_stats(msa_coords[meta.axis], meta.origin[meta.axis])
            if meta.region is None:
                meta.regions = selection.sequences if meta.axis else selection.positions
                meta.region = meta.regions.add_region(start, length)
            else:
                meta.regions.update_region(meta.region, start, length)

    def do_motion_notify_event(self, event):
        if not self.view.msa:
            return
        pos = None
        seq = None
        x = self.view.hadjustment.value + event.x
        y = self.view.vadjustment.value + event.y
        if isinstance(self.view.hadjustment, ZoomAdjustment):
            pos = int(x / self.view.hadjustment.upper * len(self.view.msa))
        if isinstance(self.view.vadjustment, ZoomAdjustment):
            seq = int(y / self.view.vadjustment.upper * len(self.view.msa.sequences))
        coord = Coordinate(pos, seq, x, y, self.view.hadjustment.upper, self.view.vadjustment.upper)
        tooltips = []
        for r in self.view.renderers.renderers:
            s = r.get_tooltip(coord)
            if s is not None:
                tooltips.append(s)
        self.set_tooltip_markup('\n'.join(tooltips)) 
        pan = self._clickdrag[2]
        if pan:
            self.view.hadjustment.value = pan.x - event.x
            self.view.vadjustment.value = pan.y - event.y
        if self._selecting:
            self._update_selection_from_motion_event(event)

    def do_key_press_event(self, event):
        key = gtk.gdk.keyval_name(event.keyval)
        handled_keys = ['Up', 'Down', 'Left', 'Right', 'Page_Up', 'Page_Down', 'Home', 'End']
        if key not in handled_keys:
            return False
        shift = bool(event.state & gtk.gdk.SHIFT_MASK)
        hdir = shift or (key in ['Left', 'Right'])
        less = key in ['Up', 'Page_Up', 'Left']
        steps = -1 if less else 1
        adj = self.view.hadjustment if hdir else self.view.vadjustment
        if event.state & gtk.gdk.CONTROL_MASK:
            if key == 'End':
                self.zoom_to_fit()
            elif key == 'Home':
                self.zoom_to_details()
            else:                
                adj.zoom_step(steps)
        else:
            if key in ['Home', 'End']:
                adj.scroll_to_edge(key == 'End')
            else:
                page = key in ['Page_Up', 'Page_Down']
                adj.scroll_step(steps, page)
        return True
        
class LayoutWidget(gtk.Table):
    def __init__(self, layout, statusbar=None):
        gtk.Table.__init__(self, 2, 2)
        if statusbar is None:
            statusbar = gtk.Statusbar()
        self.statusbar = statusbar
        self.layout = layout
        self.seqview_hbox = gtk.HBox()
        self.posview_vbox = gtk.VBox()
        self.msaview_vbox = gtk.VBox()
        self.add_msaviews(layout.msaviews)
        self.add_posviews(layout.posviews)
        self.add_seqviews(layout.seqviews)
        self.props.column_spacing = 2
        self.props.row_spacing = 2
        self.attach(self.seqview_hbox, 0, 1, 0, 1, xoptions=0)
        self.attach(self.msaview_vbox, 1, 2, 0, 1)
        self.attach(self.posview_vbox, 1, 2, 1, 2, yoptions=0)
        layout.connect('changed', self.handle_layout_changed)

    def handle_layout_changed(self, layout, change):
        if change.has_changed('msaviews'):
            if change.type == 'msaviews_added':
                self.add_msaviews(change.data)
            elif change.type == 'msaview_removed':
                self.msaview_vbox.remove(self.msaview_vbox.get_children()[change.data])
        elif change.has_changed('posviews'):
            if change.type == 'posviews_added':
                self.add_posviews(change.data)
            elif change.type == 'posview_removed':
                self.posview_vbox.remove(self.posview_vbox.get_children()[change.data])
        elif change.has_changed('seqviews'):
            if change.type == 'seqviews_added':
                self.add_seqviews(change.data)
            elif change.type == 'seqview_removed':
                self.seqview_hbox.remove(self.seqview_hbox.get_children()[change.data])

    def add_msaviews(self, msaviews):
        for msaview in msaviews:
            view = ZoomView(msaview)
            view.show_all()
            self.msaview_vbox.pack_end(view)
            view.connect('leave-notify-event', self.on_msaview_leave_notify_event)
            view.connect('motion-notify-event', self.on_msaview_motion_notify_event)

    def add_posviews(self, posviews):
        for posview in posviews:
            view = ZoomView(posview)
            view.set_size_request(-1, posview.height_request)
            view.show_all()
            self.posview_vbox.pack_start(view)

    def add_seqviews(self, seqviews):
        for seqview in seqviews:
            view = ZoomView(seqview)
            view.set_size_request(seqview.width_request, -1)
            view.show_all()
            self.seqview_hbox.pack_start(view)
            
    def on_msaview_leave_notify_event(self, msaview, event):
        context_id = self.statusbar.get_context_id('msaview_mouse_position')
        self.statusbar.pop(context_id)

    def on_msaview_motion_notify_event(self, msaview, event):
        context_id = self.statusbar.get_context_id('msaview_mouse_position')
        self.statusbar.pop(context_id)
        msa = self.layout.parent
        if not msa:
            return
        pos = int((event.x + self.layout.hadjustment.value) / self.layout.hadjustment.upper * len(msa))
        seq = int((event.y + self.layout.vadjustment.value) / self.layout.vadjustment.upper * len(msa.sequences))
        if pos >= len(msa) or seq >= len(msa.sequences):
            return
        if not msa.ungapped[seq,pos]:
            msg = "[%s,%s] %s %s-" % (seq + 1, pos + 1, msa.ids[seq], sum(msa.ungapped[seq,:pos]))
        else:
            context_length = 3
            unaligned = msa.unaligned[seq]
            unaligned_pos = sum(msa.ungapped[seq,:pos])
            leading = unaligned[max(0, unaligned_pos-context_length):unaligned_pos]
            trailing = unaligned[unaligned_pos + 1:unaligned_pos + context_length + 1]
            context = "%s[%s]%s" % (leading, unaligned[unaligned_pos], trailing)
            msg = "[%s,%s] %s %s %s" % (seq + 1, pos + 1, msa.ids[seq], unaligned_pos + 1, context)
        self.statusbar.push(context_id, msg)

class ExportImageDialog(gtk.Dialog):
    setting_order = ['file', 'format', 'paper', 'heading', 'scale']
    formats = ['PDF', 'PNG', 'PS', 'SVG']
    scales = ['Fill', 'Detail', 'Custom:', 'Current']
    paper_independent_scales = ['Detail', 'Current', 'Custom:']

    def __init__(self, msaview_gui):
        dialog_options = gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT
        action_buttons = (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL, gtk.STOCK_SAVE, gtk.RESPONSE_OK) 
        gtk.Dialog.__init__(self, "Export image", msaview_gui.window, dialog_options, action_buttons)
        self.set_default_response(gtk.RESPONSE_OK)
        self.msaview_gui = msaview_gui
        t = gtk.Table(2, 6)
        t.set_col_spacings(5)
        t.set_row_spacings(5)
        self.vbox.pack_start(t)
        def position(name, type='control'):
            y = self.setting_order.index(name)
            if type == 'label':
                return [0, 1, y, y+1] 
            return [1, 2, y, y+1]
        # Format...
        self.format = self.msaview_gui.image_format.lower()
        self.format_combobox = gtk.combo_box_new_text()
        for s in self.formats:
            self.format_combobox.append_text(s)
        self.format_combobox.set_active(self.formats.index(self.format.upper()))
        format_label = gtk.Label('F_ormat:')
        format_label.props.use_underline = True
        format_label.set_mnemonic_widget(self.format_combobox)
        t.attach(format_label, *position('format', 'label'))
        t.attach(self.format_combobox, *position('format'))
        # File...
        file_hbox = gtk.HBox()
        self.file_entry = gtk.Entry()
        self.file_entry.props.activates_default = True
        if msaview_gui.msa.path:
            self.file_entry.set_text("%s.%s" % (msaview_gui.msa.path, self.format_combobox.get_active_text().lower()))
        browse_button = gtk.Button('_Browse...', use_underline=True)
        file_hbox.pack_start(self.file_entry)
        file_hbox.pack_start(browse_button)
        file_label = gtk.Label('_File:')
        file_label.props.use_underline = True
        file_label.set_mnemonic_widget(self.file_entry)
        t.attach(file_label, *position('file', 'label'))
        t.attach(file_hbox, *position('file'))
        # Paper...
        self.page_setup = msaview_gui.page_setup
        self._page_setup = self.page_setup or gtk.PageSetup()
        paper_vbuttonbox = gtk.VButtonBox()
        page_setup_button = gtk.Button('P_age setup...', use_underline=True)
        self.paper_radiobutton = gtk.RadioButton(None, '%s _Paper' % self._page_setup.get_paper_size().get_display_name(), use_underline=True)
        if not self.page_setup:
            self.paper_radiobutton.set_active(False)
        page_setup_hbox = gtk.HBox()
        page_setup_hbox.pack_start(self.paper_radiobutton)
        page_setup_hbox.pack_start(page_setup_button)
        paper_vbuttonbox.add(page_setup_hbox)
        paper_vbuttonbox.add(gtk.RadioButton(self.paper_radiobutton, 'Fit to _MSA', use_underline=True))
        t.attach(gtk.Label('Paper:'), *position('paper', 'label'))
        t.attach(paper_vbuttonbox, *position('paper'))
        # Heading...
        self.heading_checkbutton = gtk.CheckButton('Include filename _heading', use_underline=True)
        self.heading_checkbutton.set_active(True)
        t.attach(gtk.Label('Heading:'), *position('heading', 'label'))
        t.attach(self.heading_checkbutton, *position('heading'))
        # Scale...
        self.scale = msaview_gui.scale
        scale_hbox = gtk.HBox()
        self.scale_combobox = gtk.combo_box_new_text()
        self._populate_scale_combobox(self.page_setup is None)
        self.scale_custom_entry = gtk.Entry()
        self.scale_custom_entry.props.activates_default = True
        self.scale_custom_entry.set_tooltip_text('Cell proportions (WxH) or just a number for square cells.')
        self.scale_custom_entry.set_sensitive(False)
        scale_hbox.pack_start(self.scale_combobox)
        scale_hbox.pack_start(self.scale_custom_entry)
        scale_label = gtk.Label('Sca_le:')
        scale_label.props.use_underline = True
        scale_label.set_mnemonic_widget(self.scale_combobox)
        t.attach(scale_label, *position('scale', 'label'))
        t.attach(scale_hbox, *position('scale'))
        t.show_all()
        # Connections
        self._scale_ok = True
        self._filename_ok = True
        self.file_entry.connect('changed', self.on_file_entry_changed)
        page_setup_button.connect('clicked', self.on_page_setup_button_clicked)
        for r in self.paper_radiobutton.get_group():
            r.connect('clicked', self.on_paper_radiobutton_clicked)
        self.scale_custom_entry.connect('changed', self.on_scale_custom_entry_changed)
        self.scale_combobox.connect('changed', self.on_scale_combobox_changed)
        self.format_combobox.connect('changed', self.on_format_combobox_changed)

    def on_file_entry_changed(self, widget):
        self._filename_ok = False
        path = widget.get_text()
        if not os.path.isdir(path):
            dir, file = os.path.split(path)
            self._filename_ok = bool((os.path.isdir(dir) if dir else True) and file)
        if self._filename_ok:
            widget.modify_base(gtk.STATE_NORMAL, gtk.gdk.color_parse("white"))
        else:
            widget.modify_base(gtk.STATE_NORMAL, gtk.gdk.color_parse("#fdd"))
        self.validate()

    def on_page_setup_button_clicked(self, widget):
        self._page_setup = gtk.print_run_page_setup_dialog(self, self._page_setup, gtk.PrintSettings())
        mod = {gtk.PAGE_ORIENTATION_PORTRAIT: '',
               gtk.PAGE_ORIENTATION_LANDSCAPE: ' (Landscape)',
               gtk.PAGE_ORIENTATION_REVERSE_PORTRAIT: ' (Reversed)',
               gtk.PAGE_ORIENTATION_REVERSE_LANDSCAPE: ' (Landscape reversed)'}
        paper_name = self._page_setup.get_paper_size().get_display_name()
        extra = mod[self._page_setup.get_orientation()]
        self.paper_radiobutton.set_label('%s _Paper' % paper_name + extra)
        if self.page_setup is not None:
            self.page_setup = self._page_setup

    def on_paper_radiobutton_clicked(self, widget):
        if self.paper_radiobutton.get_active():
            self.page_setup = self._page_setup
            self._populate_scale_combobox(paper_independent=False)
        else:
            self.page_setup = None
            self._populate_scale_combobox(paper_independent=True)

    def on_scale_custom_entry_changed(self, widget):
        try:
            scale = None
            if self.scale_combobox.get_active_text() != 'Fill':
                scale = [float(s.strip()) for s in widget.get_text().split('x')]
                assert 1 <= len(scale) <= 2
            self.scale = scale
            self._scale_ok = True
            widget.modify_base(gtk.STATE_NORMAL, gtk.gdk.color_parse("white"))
        except:
            raise
            widget.modify_base(gtk.STATE_NORMAL, gtk.gdk.color_parse("#fdd"))
            self.scale = None
            self._scale_ok = False
        self.validate()

    def on_scale_combobox_changed(self, scale_combobox):
        scale_choice = self.scale_combobox.get_active_text()
        if scale_choice == 'Custom:':
            self.scale_custom_entry.set_sensitive(True)
            self.on_scale_custom_entry_changed(self.scale_custom_entry)
            return 
        self.set_response_sensitive(-5, True)
        self.scale_custom_entry.set_sensitive(False)
        if scale_choice == 'Fill':
            self.scale = None
        elif scale_choice == 'Detail':
            detail_width, detail_height = self.msaview_gui.layout.get_detail_size()
            self.scale = (float(detail_width) / len(self.msaview_gui.msa), 
                          float(detail_height) / len(self.msaview_gui.msa.sequences))
        elif scale_choice == 'Current':
            self.scale = (self.msaview_gui.hadjustment.upper / len(self.msaview_gui.msa),
                          self.msaview_gui.vadjustment.upper / len(self.msaview_gui.msa.sequences))
        scale_literal = ''
        if self.scale:
            scale_literal = 'x'.join('%.2f' % n for n in self.scale)
        self.scale_custom_entry.set_text(scale_literal)

    def validate(self):
        self.set_response_sensitive(-5, self._filename_ok and self._scale_ok)

    def _populate_scale_combobox(self, paper_independent):
        items = self.paper_independent_scales if paper_independent else self.scales
        current = self.scale_combobox.get_active_text() or 'Fill'
        self.scale_combobox.get_model().clear()
        for s in items:
            self.scale_combobox.append_text(s)
        i = items.index(current) if current in items else items.index('Detail')  
        self.scale_combobox.set_active(i)

    def on_format_combobox_changed(self, format_combobox):
        new_format = self.format_combobox.get_active_text().lower()
        filename = self.file_entry.get_text()
        if filename.endswith('.' + self.format):
            filename = filename.rsplit('.', 1)[0] + '.' + new_format  
        self.file_entry.set_text(filename)
        self.format = new_format

class PositionsRegionSelectionWidget(gtk.Table):
    def __init__(self, msa, label_text='_Region'):
        gtk.Table.__init__(self, 2, 2)
        self.msa = msa
        self.boundaries = None
        self.regex = True
        self.set_col_spacings(3)
        self.default_tooltip = 'Defines a region using [SEQ/]FIRST[:LAST].'
        self.region_entry = gtk.Entry()
        self.region_entry.set_tooltip_text(self.default_tooltip)
        self.region_entry.props.activates_default = True
        region_label = gtk.Label(label_text)
        region_label.props.use_underline = True
        region_label.set_mnemonic_widget(self.region_entry)
        self.regex_checkbutton = gtk.CheckButton('Use _regular expressions for sequence IDs', use_underline=True)
        self.regex_checkbutton.set_active(self.regex)
        self.attach(region_label, 0, 1, 0, 1)
        self.attach(self.region_entry, 1, 2, 0, 1)
        self.attach(self.regex_checkbutton, 1, 2, 1, 2)
        self.region_entry.connect('changed', self.on_region_entry_changed)
        self.regex_checkbutton.connect('clicked', self.on_regex_checkbutton_clicked)
        self.show_all()

    def _parse_literal(self, region_def):
        return msa.parse_position_region_literal(region_def, self.regex)

    def on_region_entry_changed(self, entry):
        region_def = entry.get_text()
        try:
            self.boundaries = self._parse_literal(region_def)
        except msa.ParseError, e:
            self.boundaries = None
            entry.set_tooltip_text(str(e))
            entry.modify_base(gtk.STATE_NORMAL, gtk.gdk.color_parse("#fdd"))
            return
        entry.set_tooltip_text(self.default_tooltip)
        entry.modify_base(gtk.STATE_NORMAL, gtk.gdk.color_parse("white"))

    def on_regex_checkbutton_clicked(self, checkbutton):
        self.regex = checkbutton.get_active()
        self.region_entry.emit('changed') 
            
class SequencesRegionSelectionWidget(PositionsRegionSelectionWidget):
    def __init__(self, msa, label_text='_Region'):
        PositionsRegionSelectionWidget.__init__(self, msa, label_text)
        self.default_tooltip = 'Defines a region using FIRST[:LAST].'
        self.region_entry.set_tooltip_text(self.default_tooltip)
        
    def _parse_literal(self, region_def):
        return msa.parse_sequence_region_literal(region_def, self.regex)
        
class PositionsRegionDialog(gtk.Dialog):
    region_selection_widget_class = PositionsRegionSelectionWidget
    
    def __init__(self, title, msaview_gui):
        self.boundaries = None
        dialog_options = gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT
        action_buttons = (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL, gtk.STOCK_OK, gtk.RESPONSE_OK) 
        gtk.Dialog.__init__(self, title, msaview_gui.window, dialog_options, action_buttons)
        self.set_default_response(gtk.RESPONSE_OK)
        self.region_selection = self.__class__.region_selection_widget_class(msaview_gui.msa)
        self.vbox.pack_start(self.region_selection)
        self.region_selection.region_entry.connect('changed', self.on_region_entry_changed)
        self.on_region_entry_changed(self.region_selection.region_entry)
        self.show_all()
        
    def on_region_entry_changed(self, entry):
        self.boundaries = self.region_selection.boundaries
        self.set_response_sensitive(-5, bool(self.boundaries))

class SequencesRegionDialog(PositionsRegionDialog):
    region_selection_widget_class = SequencesRegionSelectionWidget

class AreaDialog(gtk.Dialog):
    def __init__(self, title, msaview_gui):
        self.position_boundaries = None
        self.sequence_boundaries = None
        dialog_options = gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT
        action_buttons = (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL, gtk.STOCK_OK, gtk.RESPONSE_OK) 
        gtk.Dialog.__init__(self, title, msaview_gui.window, dialog_options, action_buttons)
        self.set_default_response(gtk.RESPONSE_OK)
        self.position_selection = PositionsRegionSelectionWidget(msaview_gui.msa, '_Positions')
        #self.position_selection.props.activates_default = True
        self.vbox.pack_start(self.position_selection)
        self.sequence_selection = SequencesRegionSelectionWidget(msaview_gui.msa, '_Sequences')
        #self.sequence_selection.props.activates_default = True
        self.vbox.pack_start(self.sequence_selection)
        self.vbox.set_spacing(5)
        self.position_selection.region_entry.connect('changed', self.on_position_region_entry_changed)
        self.sequence_selection.region_entry.connect('changed', self.on_sequence_region_entry_changed)
        self.on_position_region_entry_changed(self.position_selection.region_entry)
        self.show_all()
        
    def on_position_region_entry_changed(self, entry):
        self.position_boundaries = self.position_selection.boundaries
        self.set_response_sensitive(-5, bool(self.position_boundaries and self.sequence_boundaries))

    def on_sequence_region_entry_changed(self, entry):
        self.sequence_boundaries = self.sequence_selection.boundaries
        self.set_response_sensitive(-5, bool(self.position_boundaries and self.sequence_boundaries))

def run_dialog(dialog, action, error_label_text='Error'):
    while True:
        if dialog.run() != gtk.RESPONSE_OK:
            return
        try:
            return action(dialog)
        except Exception, e:
            if True:
                print "Printing debug traceback from gui run dialog function!"
                import traceback
                traceback.print_exc()
            dialog.hide()
            run_error_dialog(dialog.get_parent(), error_label_text, e)
            dialog.show_all()
            continue
        
class PresetViewer(gtk.HPaned):
    def __init__(self, filter=None, preset_registry=None):
        gtk.HPaned.__init__(self)
        if filter is None:
            filter = lambda name: True 
        self.filter = filter
        if preset_registry is None:
            preset_registry = presets
        self.preset = None
        self.presets = preset_registry
        column_names = ['Name', 'Location']
        self.treeview = gtk.TreeView()
        self.build_model()
        self.columns = [None] * len(column_names)
        text_renderer = gtk.CellRendererText()
        for i, df in enumerate([self.get_preset_name, self.get_preset_location]):
            self.columns[i] = gtk.TreeViewColumn(column_names[i], text_renderer)
            self.columns[i].set_cell_data_func(text_renderer, df)
            self.treeview.append_column(self.columns[i])
        self.treeview.props.search_column = 0
        self.columns[0].add_attribute(text_renderer, 'text', 0)
        s1 = gtk.ScrolledWindow()
        s1.add(self.treeview)
        self.add1(s1)
        self.preview = gtk.TextView()
        self.preview.props.editable = False
        s2 = gtk.ScrolledWindow()
        s2.add(self.preview)
        self.add2(s2)
        self.set_position(400)
        self.show_all()
        self.set_size_request(-1, -1)

        ui_xml = """
        <popup>
          <menuitem action="save"/>
          <menuitem action="delete"/>
          <menuitem action="export"/>
        </popup>
        """
        actions = [('save', gtk.STOCK_SAVE, "_Save as user preset", '<Control>s', 'Add the preset to the user preset file.', self.on_action_save_activate),
                   ('delete', gtk.STOCK_REMOVE, "_Delete user preset", 'Delete', 'Remove the preset from the user preset file.', self.on_action_delete_activate),
                   ('export', gtk.STOCK_SAVE_AS, "_Export...", '<Control><Shift>s', 'Add the preset to a custom preset file.', self.on_action_export_activate),
                   ]
        self.ui = gtk.UIManager() 
        self.ui.add_ui_from_string(ui_xml)
        action_group = gtk.ActionGroup('preset_viewer')
        action_group.add_actions(actions)
        self.ui.insert_action_group(action_group, -1)
        
        self.treeview.connect('button-press-event', self.on_button_press_event)
        self.treeview.connect('cursor-changed', self.on_cursor_changed)
    
    def build_model(self):
        self.model = gtk.ListStore(str)
        for name in sorted(self.presets.presets):
            if self.filter(name):
                self.model.append([name])
        self.treeview.set_model(self.model)
        
    def get_preset_name(self, column, cell, model, iter):
        cell.props.text = model.get_value(iter, 0)

    def get_preset_location(self, column, cell, model, iter):
        name = model.get_value(iter, 0)
        cell.props.text = self.presets.get_preset(name).presetfile
        
    def on_cursor_changed(self, treeview):
        path = self.treeview.get_cursor()[0]
        if not path:
            return
        name = self.model.get_value(self.model.get_iter(path), 0)
        preset = presets.get_preset(name)
        self.preview.props.buffer.props.text = self.presets.get_xml(name)
        self.preset = name
        actions = dict((a.get_name(), a) for a in self.ui.get_action_groups()[0].list_actions())
        actions['save'].set_sensitive(preset.presetfile != USER_PRESET_FILE)
        actions['delete'].set_sensitive(preset.presetfile == USER_PRESET_FILE)

    def on_button_press_event(self, treeview, event):
        if event.button == 3:
            x = int(event.x)
            y = int(event.y)
            pathinfo = self.treeview.get_path_at_pos(x, y)
            if pathinfo is not None:
                path, col, cellx, celly = pathinfo
                self.treeview.grab_focus()
                self.treeview.set_cursor(path, col, 0)
                self.ui.get_widget('/popup').popup(None, None, None, event.button, event.time)
            return 1
        
    def on_action_save_activate(self, action):
        path, column = self.treeview.get_cursor()
        model = self.treeview.props.model
        preset_name = model.get_value(model.get_iter(path), 0)
        try:
            save_to_user_preset_file(preset_name)
        except Exception, e:
            run_error_dialog(self.get_toplevel(), 'Save as user preset failed', e)
            return
        presets.refresh_presets()
        self.build_model()
        try:
            self.treeview.set_cursor(path)
        except:
            pass

    def on_action_delete_activate(self, action):
        path, column = self.treeview.get_cursor()
        model = self.treeview.props.model
        preset_name = model.get_value(model.get_iter(path), 0)
        try:
            remove_from_user_preset_file(preset_name)
        except Exception, e:
            run_error_dialog(self.get_toplevel(), 'User preset removal failed', e)
        presets.refresh_presets()
        self.build_model()
        try:
            self.treeview.set_cursor(path)
        except:
            pass

    def on_action_export_activate(self, action):
        path, column = self.treeview.get_cursor()
        model = self.treeview.props.model
        preset_name = model.get_value(model.get_iter(path), 0)
        buttons = (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL, gtk.STOCK_SAVE, gtk.RESPONSE_ACCEPT)
        d = gtk.FileChooserDialog('Save to preset file', self.get_toplevel(), gtk.FILE_CHOOSER_ACTION_SAVE, buttons)
        mxml_filter_name = 'Msaview xml (*.mxml)'
        for name, pattern in [(mxml_filter_name, '*.mxml'), ('All files', '*')]:
            file_filter = gtk.FileFilter()
            file_filter.add_pattern('*.mxml')
            file_filter.set_name(name)
            d.add_filter(file_filter)
        if not d.run() == gtk.RESPONSE_ACCEPT:
            d.destroy()
            return
        filename = d.get_filename()
        if d.props.filter.get_name() == mxml_filter_name and not filename.endswith('.mxml'):
            filename += '.mxml'
        try:
            save_to_preset_file(filename, preset_name)
        except Exception, e:
            run_error_dialog(self.get_toplevel(), 'Preset export failed', e)
        #presets.refresh_presets()
        self.build_model()
        try:
            self.treeview.set_cursor(path)
        except:
            pass
        d.destroy()
        
class PresetManagerDialog(gtk.Dialog):
    def __init__(self, title, parent_window, buttons=None, filter=None):
        dialog_options = gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT
        if not buttons:
            buttons = (gtk.STOCK_CLOSE, gtk.RESPONSE_OK) 
        gtk.Dialog.__init__(self, title, parent_window, dialog_options, buttons)
        self.set_default_response(gtk.RESPONSE_OK)
        self.preset_viewer = PresetViewer(filter)
        self.vbox.pack_start(self.preset_viewer)
        self.set_size_request(800, 400)
        self.show_all()
        self.set_size_request(-1, -1)

class ComponentTreeBrowser(gtk.TreeView):
    ui_xml = """
    <popup>
      <menuitem action="configure"/>
      <menuitem action="add"/>
      <menuitem action="remove"/>
      <menuitem action="create_preset"/>
    </popup>
    """
    def __init__(self, root):
        gtk.TreeView.__init__(self)
        self.props.has_tooltip = True
        self.connect_after('query-tooltip', self.query_tooltip)
        self.root = root
        self.props.enable_tree_lines = True
        self.column_names = ['Classname', 'Name', 'Preset']
        self.columns = [None] * len(self.column_names)
        icon_cell_renderer = gtk.CellRendererPixbuf()
        self.columns[0] = gtk.TreeViewColumn(self.column_names[0], icon_cell_renderer)
        self.columns[0].set_cell_data_func(icon_cell_renderer, self.get_row_icon)
        name_cell_renderer = gtk.CellRendererText()
        self.columns[0].pack_start(name_cell_renderer, True)
        self.columns[0].set_cell_data_func(name_cell_renderer, self.get_row_classname)
        self.append_column(self.columns[0])

        self.columns[1] = gtk.TreeViewColumn(self.column_names[1], name_cell_renderer)
        self.columns[1].set_cell_data_func(name_cell_renderer, self.get_row_name)
        self.append_column(self.columns[1])

        self.columns[2] = gtk.TreeViewColumn(self.column_names[2], name_cell_renderer)
        self.columns[2].set_cell_data_func(name_cell_renderer, self.get_row_preset)
        self.append_column(self.columns[2])

        self.build_model(root)
        
        actions = [('configure', gtk.STOCK_PREFERENCES, "_Configure...", '<Control>c', 'Configure the component option.', self.on_action_add_activate),
                   ('add', gtk.STOCK_ADD, "_Integrate component...", '<Control>a', 'Integrate a new component into the tree.', self.on_action_add_activate),
                   ('remove', gtk.STOCK_REMOVE, "_Remove component...", 'Delete', 'Remove the component and its descendants from the tree.', self.on_action_remove_activate),
                   ('create_preset', gtk.STOCK_SAVE, "_Create preset...", '<Control>p', 'Create a preset from the subtree.', self.on_action_create_preset_activate),
                   ]
        self.ui = gtk.UIManager() 
        self.ui.add_ui_from_string(self.ui_xml)
        action_group = gtk.ActionGroup('component_tree_browser')
        action_group.add_actions(actions)
        self.ui.insert_action_group(action_group, -1)
        
        self.connect('row-activated', self.on_row_activated)
        self.connect('cursor-changed', self.on_cursor_changed)
        self.connect('button-press-event', self.on_button_press_event)

    def query_tooltip(self, wthwidget, x, y, keyboard_mode, tooltip):
        loc = self.get_path_at_pos(*self.convert_widget_to_bin_window_coords(x, y))
        if not loc:
            return False
        path = loc[0]
        model = self.get_model()
        value = model.get_value(model.get_iter(path), 0)
        text = getattr(value, 'tooltip', None)
        if not text:
            return False
        tooltip.set_text(text)
        return True

    def build_model(self, root):
        model = gtk.TreeStore(object)
        model.append(None, [root])
        self._add_children(model, model.get_iter_first())
        self.set_model(model)

    def get_row_icon(self, column, cell, model, iter):
        value = model.get_value(iter, 0)
        if isinstance(value, str):
            cell.props.stock_id = gtk.STOCK_DIRECTORY
        elif isinstance(value, Option):
            cell.props.stock_id = gtk.STOCK_PREFERENCES
        else:
            cell.props.stock_id = gtk.STOCK_ADD

    def get_row_classname(self, column, cell, model, iter):
        value = model.get_value(iter, 0)
        if isinstance(value, Option):
            cell.props.text = value.nick #value.propname
        else:
            cell.props.text = getattr(value, 'msaview_classname', value)

    def get_row_name(self, column, cell, model, iter):
        value = model.get_value(iter, 0)
        cell.props.text = getattr(value, 'msaview_name', None)

    def get_row_preset(self, column, cell, model, iter):
        value = model.get_value(iter, 0)
        if not isinstance(value, Component):
            cell.props.text = None
            return
        if (not value.fromsettings or 
            ':' not in value.fromsettings.frompreset or
            value.fromsettings.frompreset.endswith(':default')):
            cell.props.text = None
            return
        cell.props.text = value.fromsettings.frompreset

    def _add_layout_children(self, layout, model, iter):
        if layout.msaviews:
            self._add_children(model, model.append(iter, [layout.msaviews[0]]))
        for name in ['posviews', 'seqviews']:
            it = model.append(iter, [name])
            for c in getattr(layout, name):
                self._add_children(model, model.append(it, [c]))
        l = layout.msaviews + layout.posviews + layout.seqviews
        for c in layout.children:
            if c in l:
                continue 
            self._add_children(model, model.append(iter, [c]))

    def _add_view_children(self, view, model, iter):
        for name in ['renderers', 'overlays']:
            it = model.append(iter, [name])
            for c in getattr(view, name):
                self._add_children(model, model.append(it, [c]))
        l = view.renderers.renderers + view.overlays
        for c in view.children:
            if c in l:
                continue 
            self._add_children(model, model.append(iter, [c]))
        for o in view.get_options():
            if o.propname not in ['renderers', 'overlays']:
                model.append(iter, [o])

    def _add_children(self, model, iter):
        component = model.get_value(iter, 0)
        if isinstance(component, Layout):
            self._add_layout_children(component, model, iter)
        elif isinstance(component, View):
            self._add_view_children(component, model, iter)
        else:
            for c in component.children:
                self._add_children(model, model.append(iter, [c]))
            for o in component.get_options():
                child_iter = model.append(iter, [o])
                tooltip = gtk.Tooltip()
                tooltip.set_text(o.tooltip)
                self.set_tooltip_row(tooltip, model.get_path(child_iter))

    def on_row_activated(self, treeview, path, column):
        model = self.get_model()
        value = model.get_value(model.get_iter(path), 0)
        if isinstance(value, Option):
            d = SimpleOptionConfigDialog(value)
            d.run()
            d.destroy()
            return
        pattern = ''
        if isinstance(value, str):
            pattern = value
            value = model.get_value(model.get_iter(path[:-1]), 0)
            if pattern.endswith('views'):
                pattern = 'view.' + pattern[:3]
            elif pattern in ['renderers', 'overlays']:
                pattern = pattern[:-1] + '.'
        filter = lambda name: isinstance(presets.get_preset(name), ComponentSetting) and name.startswith(pattern)
        buttons = (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL, gtk.STOCK_ADD, gtk.RESPONSE_OK)
        dialog= PresetManagerDialog('Integrate component preset', self.get_toplevel(), buttons, filter)
        run_dialog(dialog, lambda d: value.integrate_descendant(d.preset_viewer.preset), 'Integration failed')
        self.build_model(self.root)
        dialog.preset_viewer.treeview.set_cursor(path)
        self.expand_to_path(path)
        dialog.destroy()

    def on_cursor_changed(self, treeview):
        path, column = self.get_cursor()
        value = None
        if path:
            unremovable = (Root, msa.MSA, Layout)
            value = self.props.model.get_value(self.props.model.get_iter(path), 0)
        if isinstance(value, Component):
            for a in self.ui.get_action_groups()[0].list_actions():
                if a.get_name() == 'remove':
                    a.set_sensitive(not isinstance(value, unremovable))
                else:
                    a.set_sensitive(a.get_name() != 'configure')
                a.set_visible(a.get_name() != 'configure')
        elif isinstance(value, Option):
            for a in self.ui.get_action_groups()[0].list_actions():
                a.set_sensitive(a.get_name() == 'configure')
                a.set_visible(a.get_name() == 'configure')
        else:
            for a in self.ui.get_action_groups()[0].list_actions():
                a.set_sensitive(a.get_name() not in ['remove', 'create_preset'])
                a.set_visible(a.get_name() != 'configure')
        
    def on_button_press_event(self, treeview, event):
        if event.button == 3:
            x = int(event.x)
            y = int(event.y)
            pathinfo = self.get_path_at_pos(x, y)
            if pathinfo is not None:
                path, col, cellx, celly = pathinfo
                self.grab_focus()
                self.set_cursor(path, col, 0)
                self.ui.get_widget('/popup').popup(None, None, None, event.button, event.time)
            return 1
        
    def on_action_add_activate(self, action):
        self.on_row_activated(self, *self.get_cursor())

    def on_action_remove_activate(self, action):
        path, column = self.get_cursor()
        value = self.props.model.get_value(self.props.model.get_iter(path), 0)
        try:
            value.unparent()
        except Exception, e:
            run_error_dialog(self.get_toplevel(), 'Component removal failed', e)
        self.build_model(self.root)
        self.set_cursor(path[:-1] or (0,))
        self.expand_to_path(path[:-1] or (0,))

    def on_action_create_preset_activate(self, action):
        path, column = self.get_cursor()
        value = self.props.model.get_value(self.props.model.get_iter(path), 0)
        dialog_options = gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT
        buttons = (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL, gtk.STOCK_OK, gtk.RESPONSE_OK) 
        dialog = gtk.Dialog('Preset name', self.get_toplevel(), dialog_options, buttons)
        dialog.set_default_response(gtk.RESPONSE_OK)        
        label = gtk.Label()
        label.set_text('Enter a name for your preset:')
        dialog.vbox.pack_start(label)
        dialog.entry = gtk.Entry()
        dialog.entry.props.activates_default = True
        dialog.vbox.pack_start(dialog.entry)
        dialog.show_all()
        preset_name_regex = re.compile('^[A-Za-z0-9_]+$')
        def validate_preset_name(d):
            text = d.entry.get_text().strip()
            if not preset_name_regex.match(text):
                raise ValueError("preset names must be purely alphanumerical")
            return text
        name = run_dialog(dialog, validate_preset_name, 'Bad preset name')
        dialog.destroy()
        if name is None:
            return
        full_preset_name = value.msaview_classname + ':' + name
        try:
            presets.add_builtin(full_preset_name, value)
            preset = presets.get_preset(full_preset_name)
            preset.presetfile = '<TEMPORARY>'     
        except Exception, e:
            run_error_dialog(self.get_toplevel(), 'Preset creation failed', e)
            import traceback
            traceback.print_exc()
            return
        self.build_model(self.root)
        self.set_cursor(path[:-1] or (0,))
        self.expand_to_path(path[:-1] or (0,))
        preset_manager = PresetManagerDialog('New preset', self.get_toplevel(), None, lambda s: s==full_preset_name)
        preset_manager.run()
        preset_manager.destroy()

class ComponentTreeDialog(gtk.Dialog):
    def __init__(self, title, msaview_gui):
        dialog_options = gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT
        action_buttons = (gtk.STOCK_CLOSE, gtk.RESPONSE_OK) 
        gtk.Dialog.__init__(self, title, msaview_gui.window, dialog_options, action_buttons)
        self.tree = ComponentTreeBrowser(msaview_gui.root)
        self.add_accel_group(self.tree.ui.get_accel_group())
        s = gtk.ScrolledWindow()
        s.add(self.tree)
        self.vbox.pack_start(s)
        self.set_size_request(600, 400)
        self.show_all()
        self.set_size_request(-1, -1)

class GUI(object):
    ui_xml = """
    <ui>
      <menubar>
        <menu action="file">
          <menuitem action="open"/>
          <menuitem action="import_presets"/>
          <separator/>
          <menuitem action="preset_manager"/>
          <menuitem action="component_tree_browser"/>
          <separator/>
          <menuitem action="page_setup"/>
          <menuitem action="export_image"/>
          <separator/>
          <menuitem action="quit"/>
        </menu>
        <menu action="edit">
          <menu action="copy">
            <menuitem action="copy_sequences"/>
            <menuitem action="copy_ids"/>
          </menu>
          <menu action="select">
            <menuitem action="select_positions"/>
            <menuitem action="select_sequences"/>
            <menuitem action="select_area"/>
            <menuitem action="select_all"/>
            <menuitem action="deselect"/>
          </menu>
        </menu>
        <menu action="view">
          <menuitem action="zoom_positions"/>
          <menuitem action="zoom_sequences"/>
          <menuitem action="zoom_to_fit"/>
          <menuitem action="zoom_to_details"/>
        </menu>
      </menubar>
    </ui>
    """
    actions = [('file', None, '_File'),
               ('export_image', gtk.STOCK_SAVE, "_Export image...", '<Control>s', 'Save an MSA image file.'),
               ('open', gtk.STOCK_OPEN, None, '<Control>o', 'Open a fasta MSA file.'),
               ('import_presets', None, '_Import presets...', '<Control><Shift>m', 'Import a Msaview XML preset file.'),
               ('preset_manager', None, "_Preset manager...", '<Control><Shift>p', 'Manage the preset library.'),
               ('component_tree_browser', gtk.STOCK_PREFERENCES, "Configure _layout...", '<Control><Shift>l', 'Configure the current component tree.'),
               ('page_setup', None, "P_age setup...", None, 'Configure paper size and margins.'),
               ('quit', gtk.STOCK_QUIT, None, '<Control>w', 'Quit the program.'),
               
               ('edit', None, '_Edit'),
               
               ('copy', None, '_Copy', None, None),
               ('copy_sequences', gtk.STOCK_COPY, "Copy _sequences", '<Control>c', 'Copy selected residues.'),
               ('copy_ids', gtk.STOCK_COPY, "Copy _identifiers", '<Control><Shift>c', 'Copy selected sequence identifiers.'),
               
               ('select', None, '_Select', None, None),
               ('select_positions', None, "Select _positions...", '<Control>f', 'Select positions based on indexes or motifs.'),
               ('select_sequences', None, "Select _sequences...", '<Control><Shift>f', 'Select sequences based on indexes or motifs.'),
               ('select_area', None, "Select a_reas...", '<Control><Shift><Alt>f', 'Select areas based on indexes or motifs.'),
               ('select_all', None, "Select _all...", '<Control>a', 'Select everything.'),
               ('deselect', None, "_Clear selection", 'Escape', 'Select nothing.'),

               ('view', None, '_View'),
               ('zoom_positions', None, "Zoom to _positions...", None, 'Zoom to a position region defined from indexes or motifs.'),
               ('zoom_sequences', None, "Zoom to _sequences...", None, 'Zoom to a sequence region defined from indexes or motifs.'),
               ('zoom_to_fit', None, "Zoom to _fit", None, 'Zoom to show the whole MSA.'),
               ('zoom_to_details', None, "Zoom to _details", None, 'Zoom in so that all details become visible.'),
               ]
    
    def __init__(self, root_component, page_setup=None, scale=None, image_format='pdf'):
        self.window_title_template = 'MSAView - %s'
        self.root = root_component
        self.msa = self.root.find_descendant('data.msa')
        self.msa.connect('changed', self.handle_msa_change)
        self.layout = self.msa.find_descendant('layout')
        self.window = gtk.Window()
        self.window.set_title(self.window_title_template % self.msa.path)
        self.window.connect('destroy', gtk.main_quit)
        self.ui = gtk.UIManager()
        self.ui.add_ui_from_string(self.ui_xml)
        action_group = gtk.ActionGroup('msaview_gui')
        action_group.add_actions([(t + (getattr(self, 'on_action_%s_activate' % t[0]),) if len(t) == 5 else t) for t in self.actions])
        self.ui.insert_action_group(action_group, -1)
        self.window.add_accel_group(self.ui.get_accel_group())
        vbox = gtk.VBox()
        vbox.pack_start(self.ui.get_widget('/menubar'), expand=False)
        t = gtk.Table(2,2)
        self.layout_widget = LayoutWidget(self.layout)
        t.attach(self.layout_widget, 0, 1, 0, 1)
        t.attach(gtk.VScrollbar(self.layout.vadjustment), 1, 2, 0, 1, xoptions=0)
        t.attach(gtk.HScrollbar(self.layout.hadjustment), 0, 1, 1, 2, yoptions=0)
        vbox.pack_start(t)
        vbox.pack_start(self.layout_widget.statusbar, expand=False)
        self.window.add(vbox)
        self.window.set_default_size(800, 600)
        self.window.show_all()
        self.hadjustment = self.layout.hadjustment
        self.vadjustment = self.layout.vadjustment
        if page_setup is None:
            page_setup = gtk.PageSetup()
        self.page_setup = page_setup
        self.scale = scale
        self.image_format = image_format
        
    def handle_msa_change(self, msa, changes):
        if changes.has_changed('sequences'):
            self.window.set_title(self.window_title_template % msa.path)
    
    # ACTION HANDLERS:
    
    def on_action_export_image_activate(self, action):
        d = ExportImageDialog(self)
        response = d.run()
        if response != gtk.RESPONSE_OK:
            d.destroy()
            return
        filename = d.file_entry.get_text()
        heading = d.heading_checkbutton.get_active()
        heading_text = None
        if heading:
            heading_text = self.msa.path or ''
        self.layout.save_image(filename, None, d.format, heading, d.page_setup, d.scale, heading_text)
        d.destroy()
        
    def on_action_import_presets_activate(self, action):
        buttons = (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL, gtk.STOCK_OPEN, gtk.RESPONSE_ACCEPT)
        d = gtk.FileChooserDialog('Import preset file', self.window, gtk.FILE_CHOOSER_ACTION_OPEN, buttons)
        mxml_filter_name = 'Msaview xml (*.mxml)'
        for name, pattern in [(mxml_filter_name, '*.mxml'), ('All files', '*')]:
            file_filter = gtk.FileFilter()
            file_filter.add_pattern('*.mxml')
            file_filter.set_name(name)
            d.add_filter(file_filter)
        if not d.run() == gtk.RESPONSE_ACCEPT:
            d.destroy()
            return
        filename = d.get_filename()
        try:
            f = open(filename)
            presets.import_preset_file(f)
            f.close()
        except Exception, e:
            run_error_dialog(self.get_toplevel(), 'Preset export failed', e)
        d.destroy()

    def on_action_open_activate(self, action):
        d = gtk.FileChooserDialog('Open MSA', self.window, buttons=(gtk.STOCK_CANCEL,gtk.RESPONSE_CANCEL,gtk.STOCK_OPEN,gtk.RESPONSE_OK))
        if d.run() != gtk.RESPONSE_OK:
            d.destroy()
            return
        filename = d.get_filename()
        self.window.set_title(self.window_title_template % filename)
        d.destroy()
        f = open(filename)
        self.msa.read_fasta(f)
        f.close()

    def on_action_quit_activate(self, action):
        self.window.destroy()

    def on_action_component_tree_browser_activate(self, action):
        dialog = ComponentTreeDialog('Layout configuration', self)
        dialog.tree.expand_to_path((0,0,0))
        dialog.run()
        dialog.destroy()

    def on_action_preset_manager_activate(self, action):
        dialog = PresetManagerDialog('Preset library', self.window)
        dialog.run()
        dialog.destroy()

    def on_action_page_setup_activate(self, action):
        self.page_setup = gtk.print_run_page_setup_dialog(self.window, self.page_setup, gtk.PrintSettings())
        
    def on_action_copy_activate(self, action):
        actions = dict((a.get_name(), a) for a in self.ui.get_action_groups()[0].list_actions())
        sel = self.msa.selection
        actions['copy_ids'].set_sensitive(bool(sel.sequences or sel.areas))
        actions['copy_sequences'].set_sensitive(bool(sel)) 
        
    def on_action_copy_sequences_activate(self, action):
        fasta = []
        if self.msa.selection.positions or self.msa.selection.sequences:
            if self.msa.selection.positions:
                pos_regions = self.msa.selection.positions.regions
            else:
                pos_regions = [Region(0, len(self.msa))]
            if self.msa.selection.sequences:
                seq_regions = self.msa.selection.sequences.regions
            else:
                seq_regions = [Region(0, len(self.msa.sequences))]
            for seq_region in seq_regions:
                for seq in range(seq_region.start, seq_region.start + seq_region.length):
                    id = self.msa.ids[seq]
                    description = self.msa.descriptions[seq] if self.msa.descriptions else None
                    regions = []
                    for pos_region in pos_regions:
                        regions.append(self.msa.sequences[seq][pos_region.start:pos_region.start + pos_region.length])
                    sequence = ''.join(regions)
                    wrapped = '\n'.join(sequence[i:i+60] for i in range(0, len(sequence), 60))
                    entry = '>%s%s\n%s' % (id, ' ' + description if description else '', wrapped)
                    fasta.append(entry)
        else:
            for area in self.msa.selection.areas.areas:
                for seq in range(area.sequences.start, area.sequences.start + area.sequences.length):
                    id = self.msa.ids[seq]
                    description = self.msa.descriptions[seq] if self.msa.descriptions else None
                    sequence = self.msa.sequences[seq][area.positions.start:area.positions.start + area.positions.length]
                    wrapped = '\n'.join(sequence[i:i+60] for i in range(0, len(sequence), 60))
                    entry = '>%s%s\n%s' % (id, ' ' + description if description else '', wrapped)
                    fasta.append(entry)
        for clipboard_name in ("CLIPBOARD", "PRIMARY"):
            clipboard = gtk.Clipboard(selection=clipboard_name).set_text('\n'.join(fasta))
        
    def on_action_copy_ids_activate(self, action):
        ids = []
        if self.msa.selection.sequences:
            regions = self.msa.selection.sequences.regions
        else:
            regions = (area.sequences for area in self.msa.selection.areas.areas)
        for region in regions:
            ids.extend(self.msa.ids[region.start:region.start+region.length]) 
        for clipboard_name in ("CLIPBOARD", "PRIMARY"):
            clipboard = gtk.Clipboard(selection=clipboard_name).set_text('\n'.join(ids))
        
    def on_action_select_activate(self, action):
        for a in self.ui.get_action_groups()[0].list_actions():
            a.set_sensitive(a.get_name() != 'deselect' or bool(self.msa.selection))
            
    def on_action_select_all_activate(self, action):
        self.msa.selection.areas.add_area(0, 0, len(self.msa), len(self.msa.sequences))
        
    def on_action_select_positions_activate(self, action):
        dialog = PositionsRegionDialog('Select positions', self)
        run_dialog(dialog, lambda d: self.msa.select_positions(d.boundaries), 'Selection failed')
        dialog.destroy()

    def on_action_select_sequences_activate(self, action):
        dialog = SequencesRegionDialog('Select sequences', self)
        run_dialog(dialog, lambda d: self.msa.select_sequences(d.boundaries), 'Selection failed')
        dialog.destroy()

    def on_action_select_area_activate(self, action):
        dialog = AreaDialog('Select area', self)
        run_dialog(dialog, lambda d: self.msa.select_area((d.position_boundaries, d.sequence_boundaries)), 'Selection failed')
        dialog.destroy()

    def on_action_deselect_activate(self, action):
        self.msa.selection.clear()

    def on_action_zoom_positions_activate(self, action):
        dialog = PositionsRegionDialog('Zoom to positions', self)
        region = run_dialog(dialog, lambda d: self.msa.get_position_region(d.boundaries), 'Zoom failed')
        if region:
            msa_area = self.layout.get_msa_area()
            msa_area[0] = region[0]
            msa_area[2] = region[1]
            render_area = self.layout.get_msa_render_area_for_msa_area(msa_area)
            self.layout.zoom_to_msaview_area(render_area)
        dialog.destroy()

    def on_action_zoom_sequences_activate(self, action):
        dialog = SequencesRegionDialog('Zoom to sequences', self)
        region = run_dialog(dialog, lambda d: self.msa.get_sequence_regions(d.boundaries, single=True), 'Zoom failed')
        if region:
            msa_area = self.layout.get_msa_area()
            msa_area[1] = region[0]
            msa_area[3] = region[1]
            render_area = self.layout.get_msa_render_area_for_msa_area(msa_area)
            self.layout.zoom_to_msaview_area(render_area)
        dialog.destroy()

    def on_action_zoom_to_fit_activate(self, action):
        self.layout.hadjustment.zoom_to_fit(self.layout.hadjustment.page_size)
        self.layout.vadjustment.zoom_to_fit(self.layout.vadjustment.page_size)

    def on_action_zoom_to_details_activate(self, action):
        detail = self.layout.get_detail_size()
        self.layout.hadjustment.zoom_to_size(detail[0])
        self.layout.vadjustment.zoom_to_size(detail[1])

