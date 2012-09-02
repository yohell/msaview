import os
import re

import gobject
import gtk
import pango

from color import (Color,
                   RegexColormap,
                   ResidueColormap,
                   Gradient)
from preset import (Setting,
                    presets) 
from plotting import chequers

def _make_msaview_name(component):
    try:
        return component.find_ancestor('root').descendants.name(component)
    except:
        return component.msaview_classname + '*'

class ConfigEntry(gtk.Entry):
    __gsignals__ = dict(changed='override')
    
    def __init__(self, option):
        gtk.Entry.__init__(self)
        self.option = option
        self.set_text(option.to_str())
        self.set_activates_default(True)
        self.do_changed()
        
    def set_tooltip(self, msg=None):
        if msg is None:
            msg = '%s: %s' % (self.option.nick, self.option.tooltip)
        self.set_tooltip_text(msg)
        
    def revert_value(self):
        self.set_text(self.option.to_str())
        
    def do_changed(self):
        try:
            self.option.from_str(self.get_text())
        except Exception, e:
            self.modify_base(gtk.STATE_NORMAL, gtk.gdk.color_parse("#fdd"))
            self.set_tooltip(str(e))
            self.valid = False
        else:
            self.modify_base(gtk.STATE_NORMAL, gtk.gdk.color_parse("white"))
            self.set_tooltip()
            self.valid = True
        
class ConfigCheckButton(gtk.CheckButton):
    __gsignals__ = dict(
        clicked = 'override',
        changed = (
            gobject.SIGNAL_RUN_LAST,
            gobject.TYPE_NONE,
            ()))
    
    def __init__(self, option):
        gtk.CheckButton.__init__(self)
        self.option = option
        self.set_label(option.nick)
        self.valid = True
        self.set_active(option.value)
        self.set_tooltip()
        
    def set_tooltip(self, msg=None):
        if msg is None:
            msg = '%s: %s' % (self.option.nick, self.option.tooltip)
        self.set_tooltip_text(msg)
        
    def revert_value(self):
        self.set_active(self.option.value)
        
    def do_clicked(self):
        gtk.CheckButton.do_clicked(self)
        self.option.set_value(self.get_active())
        self.emit('changed')

class ConfigSpinbutton(gtk.SpinButton):
    __gsignals__ = dict(value_changed = 'override')
    
    def __init__(self, option, adjustment, climb_rate=0.0, digits=0):
        self.option = option
        gtk.SpinButton.__init__(self, adjustment, climb_rate, digits)
        self.valid = True
        self.set_text(option.to_str())
        
    def set_tooltip(self, msg=None):
        if msg is None:
            msg = '%s: %s' % (self.option.nick, self.option.tooltip)
        self.set_tooltip_text(msg)
        
    def do_value_changed(self):
        try:
            try:
                self.option.set_value(self.get_value())
            except:
                raise ValueError("a number is required")
        except Exception, e:
            self.modify_base(gtk.STATE_NORMAL, gtk.gdk.color_parse("#fdd"))
            self.set_tooltip(str(e))
            self.valid = False
        else:
            self.modify_base(gtk.STATE_NORMAL, gtk.gdk.color_parse("white"))
            self.set_tooltip()
            self.valid = True
        self.emit('changed')

    def revert_value(self):
        self.set_value(self.option.value)

class ConfigNumber(gtk.HBox):
    __gsignals__ = dict(
        changed = (
            gobject.SIGNAL_RUN_LAST,
            gobject.TYPE_NONE,
            ()),
        activate = (
            gobject.SIGNAL_RUN_LAST,
            gobject.TYPE_NONE,
            ())
            )

    def __init__(self, option, adjustment=None, climb_rate=0.0, digits=0, hscale_lower=None, hscale_upper=None):
        gtk.HBox.__init__(self)
        self.spinbutton = ConfigSpinbutton(option, adjustment, climb_rate, digits)
        self.spinbutton_adjustment = self.spinbutton.get_adjustment()
        self.spinbutton.connect('changed', lambda button: self.emit('changed'))
        #self.spinbutton.connect('activate', lambda button: self.emit('activate'))
        if hscale_lower is None:
            hscale_lower = adjustment.lower
        if hscale_upper is None:
            hscale_upper = adjustment.upper
        self.hscale_adjustment = gtk.Adjustment(adjustment.value, hscale_lower, hscale_upper, -adjustment.step_increment)
        self.hscale = gtk.HScale(self.hscale_adjustment)
        def update_hscale_adj(spinbutton_adj):
            if self.spinbutton.valid:
                self.hscale_adjustment.set_value(self.spinbutton_adjustment.value)
        self.spinbutton_adjustment.connect_after('value-changed', update_hscale_adj) 
        self.hscale_adjustment.connect_after('value-changed', lambda adj: self.spinbutton_adjustment.set_value(self.hscale_adjustment.value)) 
        self.hscale.props.draw_value = False
        self.pack_start(self.spinbutton)
        self.pack_start(self.hscale)
        self.option = option
        self.default_config_widget = self.spinbutton

    valid = property(lambda self: self.spinbutton.valid)

    def revert_value(self):
        self.spinbutton.revert_value() 

_UNSET = []

class Option(object):
    def __init__(self, component=None, propname=None, default=_UNSET, value=_UNSET, nick=None, tooltip=None):
        self.component = component
        self.propname = propname
        if value is _UNSET:
            value = getattr(component.props, propname)
        self.value = value
        self.revert = value
        if default is _UNSET or nick is None or tooltip is None:
            pspec = getattr(component.__class__.props, propname)
        if default is _UNSET:
            default = getattr(pspec, 'default_value', value)
        self.default = default
        if nick is None:
            nick = pspec.nick
        self.nick = nick
        if tooltip is None:
            tooltip = pspec.blurb
        self.tooltip = tooltip
        
    def __repr__(self):
        name = object.__repr__(self).split()[0][1:]
        return "<%s %s>" % (name, self.propname)
        
    def set_value(self, value):
        self.value = value
        
    def parse_str(self, string):
        return string.strip()
        
    def from_str(self, string):
        self.set_value(self.parse_str(string))
        
    def to_str(self, value=_UNSET):
        if value is _UNSET:
            value = self.value
        return str(value)
        
    def create_config_widget(self):
        return ConfigEntry(self)

class BooleanOption(Option):
    true = ['true', 'yes', '1', 'enable', 'enabled', 'on']
    false = ['false', 'no', '1', 'disable', 'disabled', 'off']
    def parse_str(self, string):
        word = string.strip().lower()
        if word in self.true:
            return True
        if word in self.false:
            return False
        raise ValueError('requires a truth value, such as True, NO or 1')

    def to_str(self, value=_UNSET):
        if value is _UNSET:
            value = self.value
        if value:
            return 'True'
        return 'False'

    def create_config_widget(self):
        return ConfigCheckButton(self)

class FloatOption(Option):
    def __init__(self, component=None, propname=None, minimum=None, maximum=None, hint_minimum=None, hint_maximum=None, hint_step=0.1, hint_page=0.1, hint_digits=2, default=_UNSET, value=_UNSET, nick=None, tooltip=None):
        Option.__init__(self, component, propname, default, value, nick, tooltip)
        self.hint_step = hint_step
        self.hint_page = hint_page
        self.hint_digits = hint_digits
        if minimum is None:
            minimum = getattr(component.__class__.props, propname).minimum
        if maximum is None:
            maximum = getattr(component.__class__.props, propname).maximum
        if hint_minimum is None:
            hint_minimum = minimum
        if hint_maximum is None:
            hint_maximum = maximum
        self.minimum = minimum
        self.maximum = maximum
        self.hint_minimum = hint_minimum
        self.hint_maximum = hint_maximum
    
    def parse_str(self, string):
        try:
            return float(string.strip())
        except:
            raise ValueError('requires a floating point number')

    def create_config_widget(self):
        adj = gtk.Adjustment(self.value, self.minimum, self.maximum, self.hint_step, self.hint_page)
        return ConfigNumber(self, adj, digits=self.hint_digits, hscale_lower=self.hint_minimum, hscale_upper=self.hint_maximum)

class IntOption(FloatOption):
    def __init__(self, component=None, propname=None, minimum=None, maximum=None, hint_minimum=None, hint_maximum=None, hint_step=1, hint_page=1, default=_UNSET, value=_UNSET, nick=None, tooltip=None):
        FloatOption.__init__(self, component, propname, minimum, maximum, hint_minimum, hint_maximum, hint_step, hint_page, 0, default, value, nick, tooltip)

    def parse_str(self, string):
        try:
            return int(string.strip())
        except:
            raise ValueError('requires an integer number')

class RegexOption(Option):
    flags = re.IGNORECASE
    def parse_str(self, string):
        return re.compile(string, self.flags)

    def to_str(self, value=_UNSET):
        if value is _UNSET:
            value = self.value
        return value.pattern

class ConfigFont(gtk.HBox):
    __gsignals__ = dict(
        changed = (
            gobject.SIGNAL_RUN_LAST,
            gobject.TYPE_NONE,
            ()),
        activate = (
            gobject.SIGNAL_RUN_LAST,
            gobject.TYPE_NONE,
            ())
            )

    def __init__(self, option):
        gtk.HBox.__init__(self)
        self.font_entry = ConfigEntry(option)
        self.font_button = gtk.FontButton(option.value.to_string())
        self.pack_start(self.font_button, expand=False)
        self.pack_start(self.font_entry)
        self.font_entry.connect('changed', self.handle_font_entry_changed) 
        self.font_button.connect('font-set', self.handle_font_button_font_set) 
        self.font_entry.connect('activate', lambda e: self.emit('activate'))
        self.option = option
        self.default_config_widget = self.font_entry

    valid = property(lambda self: self.font_entry.valid)

    def handle_font_entry_changed(self, entry):
        if entry.valid:
            self.font_button.props.font_name = self.option.value.to_string()
        self.emit('changed')
        
    def handle_font_button_font_set(self, button):
        self.option.value = pango.FontDescription(button.props.font_name)
        self.revert_value()
        
    def revert_value(self):
        self.font_entry.revert_value() 

class FontOption(Option):
    def __init__(self, component=None, propname='font', default=_UNSET, value=_UNSET, nick=None, tooltip=None):
        Option.__init__(self, component, propname, default, value, nick, tooltip)
        
    def parse_str(self, string):
        return pango.FontDescription(string)

    def to_str(self, value=_UNSET):
        if value is _UNSET:
            value = self.value
        return value.to_string()

    def create_config_widget(self):
        return ConfigFont(self)

def _read_x11_colors(path=None):
    if path is None:
        path = os.path.join(os.path.split(__file__)[0], 'data', 'rgb.txt')
    f = open(path)    
    "255 250 250        "
    colors = []
    for line in f:
        if line.startswith('!'):
            continue
        colors.append([line.split('\t\t')[1].strip()])
    f.close()
    return colors

class ColorCompletion(gtk.EntryCompletion):
    system_x11_rgb_colordef_file = '/usr/share/X11/rgb.txt'
    if os.path.isfile(system_x11_rgb_colordef_file):
        _colors = _read_x11_colors(system_x11_rgb_colordef_file)
    else:
        _colors = _read_x11_colors()
    def __init__(self):
        gtk.EntryCompletion.__init__(self)
        model = gtk.ListStore(str)
        self.set_model(model)
        self.set_match_func(lambda c, k, i: c.get_model()[i][0].startswith(k))
        self.set_text_column(0)
        self.props.inline_completion = True
        self.props.inline_selection = True
        self.props.popup_set_width = False
        for c in self._colors:
            model.append(c)
        for preset_name in presets.presets:
            if not preset_name.startswith('color:'):
                continue
            model.append([preset_name[len('color:'):]])

class ConfigColor(gtk.HBox):
    __gsignals__ = dict(
        changed = (
            gobject.SIGNAL_RUN_LAST,
            gobject.TYPE_NONE,
            ()),
        activate = (
            gobject.SIGNAL_RUN_LAST,
            gobject.TYPE_NONE,
            ())
            )

    def __init__(self, option):
        gtk.HBox.__init__(self)
        self.color_entry = ConfigEntry(option)
        color_completion = ColorCompletion()
        self.color_entry.set_completion(color_completion)
        #def handle_match_selected(completion, model, iter):
        #    self.color_entry.set_text(model[iter][0])
        #    self.color_entry.set_position(-1)
        #    self.color_entry.do_changed()
        #color_completion.connect('match-selected', handle_match_selected)
        c, alpha = option.value.to_gdk_color_and_alpha()
        self.color_button = gtk.ColorButton(c)
        self.color_button.set_properties(alpha=alpha, use_alpha=True)
        self.pack_start(self.color_button, expand=False)
        self.pack_start(self.color_entry)
        self.color_entry.connect_after('changed', self.handle_color_entry_changed) 
        self.color_button.connect('color-set', self.handle_color_button_color_set) 
        self.color_entry.connect('activate', lambda e: self.emit('activate'))
        self.option = option
        self.default_config_widget = self.color_entry

    valid = property(lambda self: self.color_entry.valid)

    def handle_color_entry_changed(self, entry):
        if entry.valid:
            c, alpha = self.option.value.to_gdk_color_and_alpha()
            self.color_button.set_properties(color=c, alpha=alpha)
        self.emit('changed')
        
    def handle_color_button_color_set(self, button):
        c = button.props.color
        alpha = button.props.alpha / 65535.0
        self.option.value = Color.from_gdk_color(c, alpha)
        self.revert_value()
        
    def revert_value(self):
        self.color_entry.revert_value() 

class ColorOption(Option):
    def __init__(self, component=None, propname='color', default=_UNSET, value=_UNSET, nick=None, tooltip=None):
        if default is _UNSET:
            default = component.propdefaults[propname]
            if isinstance(default, Setting):
                default = default.get_value()
        Option.__init__(self, component, propname, default, value, nick, tooltip)
        
    def parse_str(self, string):
        try:
            return Color.from_str(string.strip())
        except:
            try:
                return presets.get_value('color:' + string.strip())
            except:
                pass
            raise ValueError('must be a color, such as navajowhite or #15a5ff')

    def to_str(self, value=_UNSET):
        if value is _UNSET:
            value = self.value
        return value.to_str()
        
    def create_config_widget(self):
        return ConfigColor(self)

class GradientPreview(gtk.DrawingArea):
    __gsignals__ = dict(expose_event='override')
    background = chequers((.4, .4, .4), (.6, .6, .6), 6)
    
    def __init__(self, gradient):
        gtk.DrawingArea.__init__(self)
        self.gradient = gradient
        
    def set_gradient(self, gradient):
        self.gradient = gradient
        self.queue_draw()
        
    def do_expose_event(self, event):
        cr = self.window.cairo_create()
        cr.rectangle(*event.area)
        cr.clip()
        self.draw(cr)
        
    def draw(self, cr):
        area = self.get_allocation()
        cr.rectangle(0, 0, area.width, area.height)
        cr.set_source(self.background)
        cr.fill_preserve()
        cr.set_source(self.gradient.to_linear_gradient(0, 0, area.width, 0))
        cr.fill()
        
class ConfigColorStop(gtk.HBox):
    __gsignals__ = dict(
        changed = (
            gobject.SIGNAL_RUN_LAST,
            gobject.TYPE_NONE,
            ())
            )

    def _create_button(self, stock, size):
        image = gtk.Image()
        image.set_from_stock(stock, size)
        button = gtk.Button()
        button.add(image)
        button.set_relief(gtk.RELIEF_NONE)
        return button

    def __init__(self, offset, color):
        gtk.HBox.__init__(self)
        self.add_button = self._create_button(gtk.STOCK_ADD, gtk.ICON_SIZE_MENU)
        self.pack_start(self.add_button, expand=False, fill=False)
        if color is None:
            self._offset = offset
            return
        self.offset_option = FloatOption(None, None, 0, 1, 0, 1, 0.01, 0.05, 2, 1, offset, 'color stop (offset)', 'where in the gradient to place the given color')
        self.offset_config = self.offset_option.create_config_widget()
        self.offset_config.child_set_property(self.offset_config.spinbutton, 'expand', False)
        self.offset_config.connect('changed', lambda w: self.emit('changed'))
        self.pack_start(self.offset_config)
        self.color_option = ColorOption(default=color, value=color, nick='color stop (color)', tooltip='the color at the given offset')
        self.color_config = self.color_option.create_config_widget()
        self.color_config.child_set_property(self.color_config.color_entry, 'expand', False)
        self.color_config.connect('changed', lambda w: self.emit('changed'))
        self.pack_start(self.color_config, expand=False)
        self.remove_button = self._create_button(gtk.STOCK_CANCEL, gtk.ICON_SIZE_MENU)
        self.pack_start(self.remove_button, expand=False, fill=False)

    valid = property(lambda self: bool(self.offset_config.valid and self.color_config.valid))
        
    def get_color(self):
        try:
            self.color_option
        except:
            return None
        return self.color_option.value

    def get_offset(self):
        try:
            self.offset_option
        except:
            return self._offset
        return self.offset_option.value

    def get_colorstop(self):
        try:
            self.offset_option
        except:
            return self._offset, None
        return self.offset_option.value, self.color_option.value

class ConfigGradient(gtk.VBox):
    __gsignals__ = dict(
        changed = (
            gobject.SIGNAL_RUN_LAST,
            gobject.TYPE_NONE,
            ()),
        activate = (
            gobject.SIGNAL_RUN_LAST,
            gobject.TYPE_NONE,
            ())
            )

    def __init__(self, option):
        gtk.VBox.__init__(self)
        self.props.spacing = 5
        self.option = option
        self.preview = GradientPreview(option.value)
        self.preview.set_size_request(16, 16)
        self.pack_start(self.preview, expand=False)
        scroll = gtk.ScrolledWindow()
        scroll.props.hscrollbar_policy = gtk.POLICY_NEVER
        scroll.props.vscrollbar_policy = gtk.POLICY_ALWAYS
        self.stop_vbox = gtk.VBox()
        self.stop_vbox.props.spacing = 10
        scroll.add_with_viewport(self.stop_vbox)
        self.pack_start(scroll)
        self.revert_value()
    
    valid = property(lambda self: False not in (c.valid for c in self.stop_vbox.get_children()[:-1]))

    def handle_colorstop_changed(self, config_widget):
        if config_widget.valid:
            reordered = sorted(self.stop_vbox.get_children(), key=lambda cs: cs.get_offset())
            gradient = Gradient()
            for i, cs_config in enumerate(reordered):
                self.stop_vbox.reorder_child(cs_config, i)
                offset, color = cs_config.get_colorstop()
                if color is not None:
                    gradient.add_colorstop(offset, color)
            self.option.value = gradient
            self.preview.set_gradient(gradient)
        self.emit('changed')
        
    def handle_add_colorstop_clicked(self, button):
        cs_configs = self.stop_vbox.get_children()
        cs_config = button.get_parent()
        offset, color = cs_config.get_colorstop()
        colorstops = list(self.option.value.colorstops)
        self.option.value = Gradient()
        self.option.value.colorstops = colorstops
        if color is None:
            if len(cs_configs) == 1:
                self.option.value.add_colorstop(0, Color(1,1,1))
            else:
                self.option.value.add_colorstop(1, cs_configs[-2].get_color())
            self.revert_value()
            return
        i = cs_configs.index(cs_config)
        if i == 0:
            self.option.value.add_colorstop(0, cs_configs[0].get_color())
        else:
            offset2, color2 = cs_configs[i - 1].get_colorstop()
            o = (offset + offset2)/2
            c = color.blend(0.5, color2)
            self.option.value.add_colorstop(o, c)
        self.revert_value()

    def handle_remove_colorstop_clicked(self, button):
        cs_configs = self.stop_vbox.get_children()
        cs_config = button.get_parent()
        i = cs_configs.index(cs_config)
        self.stop_vbox.remove(cs_config)
        colorstops = list(self.option.value.colorstops)
        self.option.value = Gradient()
        self.option.value.colorstops = colorstops
        del self.option.value.colorstops[i]
        self.revert_value()

    def revert_value(self):
        self.preview.set_gradient(self.option.value)
        for child in self.stop_vbox.get_children():
            self.stop_vbox.remove(child)
        for colorstop in self.option.value.colorstops:
            cs_config = ConfigColorStop(*colorstop)
            cs_config.connect('changed', self.handle_colorstop_changed)
            cs_config.add_button.connect('clicked', self.handle_add_colorstop_clicked)
            cs_config.remove_button.connect('clicked', self.handle_remove_colorstop_clicked)
            self.stop_vbox.pack_start(cs_config, expand=False)
        add_last = ConfigColorStop(2, None)
        add_last.add_button.connect('clicked', self.handle_add_colorstop_clicked)
        self.stop_vbox.pack_start(add_last, expand=False)
        self.stop_vbox.show_all()
        self.emit('changed')

class GradientOption(Option):
    def __init__(self, component=None, propname='gradient', default=_UNSET, value=_UNSET, nick=None, tooltip=None):
        if default is _UNSET:
            default = component.propdefaults[propname]
            if isinstance(component, Setting):
                default = default.get_value()
        Option.__init__(self, component, propname, default, value, nick, tooltip)
        self.revert = Gradient()
        self.revert.colorstops = list(self.value.colorstops) 
        self.value = Gradient()
        self.value.colorstops = list(self.revert.colorstops) 
        
    def parse_str(self, string):
        return Gradient.from_str(string.strip())
        
    def to_str(self, value=_UNSET):
        if value is _UNSET:
            value = self.value
        return value.to_str()
        
    def create_config_widget(self):
        w = ConfigGradient(self)
        w.props.height_request = 200
        return w
    
class ConfigResidueColorMapping(gtk.HBox):
    __gsignals__ = dict(
        changed = (
            gobject.SIGNAL_RUN_LAST,
            gobject.TYPE_NONE,
            ())
            )

    def _create_button(self, stock, size):
        image = gtk.Image()
        image.set_from_stock(stock, size)
        button = gtk.Button()
        button.add(image)
        button.set_relief(gtk.RELIEF_NONE)
        return button

    def __init__(self, residues, color):
        gtk.HBox.__init__(self)
        if residues is None:
            self.add_button = self._create_button(gtk.STOCK_ADD, gtk.ICON_SIZE_MENU)
            self.pack_start(self.add_button, expand=False, fill=False)
            return None
        self.key_option = Option(None, None, '', residues, 'color mapping (residues)', 'what residues to paint with the given color')
        self.key_config = self.key_option.create_config_widget()
        self.key_config.connect_after('changed', lambda w: self.emit('changed'))
        self.pack_start(self.key_config)
        self.color_option = ColorOption(default=color, value=color, nick='color mapping (color)', tooltip='the color for the given residues')
        self.color_config = self.color_option.create_config_widget()
        self.color_config.child_set_property(self.color_config.color_entry, 'expand', False)
        self.color_config.connect_after('changed', lambda w: self.emit('changed'))
        self.pack_start(self.color_config, expand=False)
        self.remove_button = self._create_button(gtk.STOCK_CANCEL, gtk.ICON_SIZE_MENU)
        self.pack_start(self.remove_button, expand=False, fill=False)

    valid = property(lambda self: self.key_config.valid and self.color_config.valid)

    def get_color(self):
        try:
            self.color_option
        except:
            return None
        return self.color_option.value

    def get_key(self):
        try:
            self.key_option
        except:
            return None
        return self.key_option.value

    def get_mapping(self):
        try:
            self.key_option
        except:
            return None, None
        return self.key_option.value, self.color_option.value

class ConfigResidueColormap(gtk.VBox):
    __gsignals__ = dict(
        changed = (
            gobject.SIGNAL_RUN_LAST,
            gobject.TYPE_NONE,
            ()),
        activate = (
            gobject.SIGNAL_RUN_LAST,
            gobject.TYPE_NONE,
            ())
            )
    colormap_class = ResidueColormap
    mapping_config_class = ConfigResidueColorMapping
     
    def __init__(self, option):
        gtk.VBox.__init__(self)
        self.props.spacing = 5
        self.option = option
        scroll = gtk.ScrolledWindow()
        scroll.props.hscrollbar_policy = gtk.POLICY_NEVER
        scroll.props.vscrollbar_policy = gtk.POLICY_ALWAYS
        self.mapping_vbox = gtk.VBox()
        self.mapping_vbox.props.spacing = 10
        scroll.add_with_viewport(self.mapping_vbox)
        self.pack_start(scroll)
        self.revert_value()

    valid = property(lambda self: False not in (c.valid for c in self.mapping_vbox.get_children()[1:]))

    def handle_mapping_changed(self, config_widget):
        if config_widget.valid:
            colormap = self.colormap_class()
            mappings = []
            for mapping_config in self.mapping_vbox.get_children():
                key, color = mapping_config.get_mapping()
                if color is not None:
                    mappings.append((key, color))
            colormap.update(mappings)
            self.option.value = colormap
        self.emit('changed')
        
    def handle_add_mapping_clicked(self, button):
        colormap = self.colormap_class()
        colormap.update(t for t in self.option.value.items())
        colormap.update([('', Color(1, 1, 1))])
        self.option.value = colormap
        self.revert_value()

    def handle_remove_mapping_clicked(self, button):
        mapping_config = button.get_parent()
        remove = mapping_config.get_key()
        colormap = self.colormap_class()
        colormap.update(t for t in self.option.value.items() if t[0] != remove)
        self.option.value = colormap
        self.revert_value()

    def revert_value(self):
        for child in self.mapping_vbox.get_children():
            self.mapping_vbox.remove(child)
        add_first = self.mapping_config_class(None, None)
        add_first.add_button.connect('clicked', self.handle_add_mapping_clicked)
        self.mapping_vbox.pack_start(add_first, expand=False)
        for mapping in self.option.value.items():
            mapping_config = self.mapping_config_class(*mapping)
            mapping_config.connect_after('changed', self.handle_mapping_changed)
            mapping_config.remove_button.connect('clicked', self.handle_remove_mapping_clicked)
            self.mapping_vbox.pack_start(mapping_config, expand=False)
        self.mapping_vbox.show_all()
        self.emit('changed')

class ResidueColormapOption(Option):
    colormap_class = ResidueColormap
    config_class = ConfigResidueColormap
    
    def __init__(self, component=None, propname='colormap', default=_UNSET, value=_UNSET, nick=None, tooltip=None):
        if default is _UNSET:
            default = component.propdefaults[propname]
            if isinstance(component, Setting):
                default = default.get_value()
        Option.__init__(self, component, propname, default, value, nick, tooltip)
        self.revert = self.colormap_class()
        self.revert.update(self.value.items()) 
        self.value = self.colormap_class()
        self.value.update(self.revert.items()) 
        
    def parse_str(self, string):
        return self.colormap_class.from_str(string.strip())
        
    def to_str(self, value=_UNSET):
        if value is _UNSET:
            value = self.value
        return value.to_str()
        
    def create_config_widget(self):
        w = self.config_class(self)
        w.props.height_request = 200
        return w

class ConfigRegexColorMapping(ConfigResidueColorMapping):
    def __init__(self, regex, color):
        gtk.HBox.__init__(self)
        self.add_button = self._create_button(gtk.STOCK_ADD, gtk.ICON_SIZE_MENU)
        self.pack_start(self.add_button, expand=False, fill=False)
        if color is None:
            return
        self.key_option = RegexOption(None, None, '', regex, 'color mapping (regex)', 'Regular expression for an msa sequence motif to paint with the given color. Groups with names starting with "paint" will be painted, or the whole match if no such groups are present.')
        self.key_config = self.key_option.create_config_widget()
        self.key_config.connect_after('changed', lambda w: self.emit('changed'))
        self.pack_start(self.key_config)
        self.color_option = ColorOption(default=color, value=color, nick='color mapping (color)', tooltip='the color for the given regular expression')
        self.color_config = self.color_option.create_config_widget()
        self.color_config.child_set_property(self.color_config.color_entry, 'expand', False)
        self.color_config.connect_after('changed', lambda w: self.emit('changed'))
        self.pack_start(self.color_config, expand=False)
        self.remove_button = self._create_button(gtk.STOCK_CANCEL, gtk.ICON_SIZE_MENU)
        self.pack_start(self.remove_button, expand=False, fill=False)

class ConfigRegexColormap(ConfigResidueColormap):
    colormap_class = RegexColormap
    mapping_config_class = ConfigRegexColorMapping

    def handle_add_mapping_clicked(self, button):
        mapping_config = button.get_parent()
        i = self.mapping_vbox.get_children().index(mapping_config)
        mappings = self.option.value.items()
        if i == len(mappings):
            color = Color(1, 1, 1)
        else:
            color = mapping_config.color_option.value
        mappings.insert(i, ('', color))
        self.option.value = self.colormap_class.from_mappings(mappings)
        self.revert_value()

    def revert_value(self):
        for child in self.mapping_vbox.get_children():
            self.mapping_vbox.remove(child)
        for mapping in self.option.value.items():
            mapping_config = self.mapping_config_class(*mapping)
            mapping_config.connect_after('changed', self.handle_mapping_valid_change)
            mapping_config.remove_button.connect('clicked', self.handle_remove_mapping_clicked)
            mapping_config.add_button.connect('clicked', self.handle_add_mapping_clicked)
            self.mapping_vbox.pack_start(mapping_config, expand=False)
        add_last = self.mapping_config_class(None, None)
        add_last.add_button.connect('clicked', self.handle_add_mapping_clicked)
        self.mapping_vbox.pack_start(add_last, expand=False)
        self.mapping_vbox.show_all()
        self.emit('changed')

class RegexColormapOption(ResidueColormapOption):
    colormap_class = RegexColormap
    config_class = ConfigRegexColormap

class ComponentListOption(object):
    def __init__(self, component=None, propname=None, value=_UNSET, nick=None):
        self.component = component
        self.propname = propname
        if value is _UNSET:
            value = getattr(component.props, propname)
        self.value = value
        if nick is None:
            nick = getattr(component.__class__.props, propname).nick
        self.nick = nick

class SimpleOptionConfigDialog(gtk.Dialog):
    def __init__(self, option):
        gtk.Dialog.__init__(self)
        if option.component is not None:
            name = _make_msaview_name(option.component)
            self.set_title('%s %s - Msaview Option Dialog' % (name, option.nick))
        else:
            self.set_title('%s - Msaview Option Dialog' % option.nick)
        option_config_widget = option.create_config_widget()
        option_config_widget.connect('changed', self.handle_change)
        value_label = gtk.Label()
        value_label.set_properties(use_underline=True, label='_Value:')
        try: 
            default_widget = option_config_widget.default_config_widget
        except AttributeError:
            default_widget = option_config_widget
        value_label.set_mnemonic_widget(default_widget)
        default_widget.props.has_focus = True
        hbox = gtk.HBox()
        hbox.pack_start(value_label, expand=False)
        hbox.pack_start(option_config_widget)
        self.vbox.pack_start(hbox)
        autoapply_button = gtk.CheckButton('Apply changes a_utomatically')
        autoapply_button.connect('clicked', self.handle_autoapply_clicked)
        apply_button = gtk.Button(stock=gtk.STOCK_APPLY)
        apply_button.connect('clicked', lambda button: self.apply())
        option_config_widget.connect('activate', lambda w: apply_button.emit('clicked'))
        default_button = gtk.Button('_Default')
        default_button.connect('clicked', self.handle_revert, True)
        revert_button = gtk.Button(stock=gtk.STOCK_REVERT_TO_SAVED)
        revert_button.connect('clicked', self.handle_revert)
        close_button = gtk.Button(stock=gtk.STOCK_CLOSE)
        close_button.connect('clicked', lambda button: self.destroy())
        self.action_area.pack_start(autoapply_button)
        self.action_area.pack_start(apply_button)
        self.action_area.pack_start(revert_button)
        self.action_area.pack_start(default_button)
        self.action_area.pack_start(close_button)
        self.option_config_widget = option_config_widget
        self.autoapply_button = autoapply_button
        self.apply_button = apply_button
        self.vbox.show_all()
        self.action_area.show_all()
        
    def handle_change(self, config_widget):
        if config_widget.valid:
            if self.autoapply_button.props.active:
                self.apply()
        self.apply_button.set_sensitive(config_widget.valid)
        
    def handle_autoapply_clicked(self, button):
        self.apply()
        self.apply_button.set_sensitive(not button.props.active) 
        
    def handle_revert(self, button, to_default=False):
        attr_name = 'default' if to_default else 'revert'
        value = getattr(self.option_config_widget.option, attr_name)
        self.option_config_widget.option.set_value(value)
        self.option_config_widget.revert_value()
        
    def apply(self):
        option = self.option_config_widget.option
        if option.component is not None:
            option.component.set_options([option])
        self.emit('response', gtk.RESPONSE_APPLY)
    
def make_options_context_menu(component):
    menu = gtk.Menu()
    def open_option_config_dialog(menuitem, option):
        dialog = SimpleOptionConfigDialog(option)
        dialog.show()
    for option in component.get_options():
        if isinstance(option, ComponentListOption):
            submenu = gtk.Menu()
            for c in option.value:
                subsubmenu = make_options_context_menu(c)
                if subsubmenu.get_children():
                    submenu_item = gtk.MenuItem(_make_msaview_name(c))
                    submenu_item.set_submenu(subsubmenu)
                    submenu.append(submenu_item)
            if submenu.get_children():
                submenu_root = gtk.MenuItem(option.nick)
                submenu_root.set_submenu(submenu)
                menu.append(submenu_root)
        elif isinstance(option, BooleanOption):
            menu_item = gtk.CheckMenuItem(option.nick)
            menu_item.set_active(option.value)
            def toggle_booloption(menu_item, opt):
                opt.set_value(not opt.value)
                opt.component.set_options([opt])
            menu_item.connect('activate', toggle_booloption, option)
            menu_item.set_tooltip_text(option.tooltip)
            menu.append(menu_item)
        elif isinstance(option, Option):
            menu_item = gtk.MenuItem(option.nick + '...')
            menu_item.connect('activate', open_option_config_dialog, option)
            menu_item.set_tooltip_text(option.tooltip)
            menu_item.show_all()
            menu.append(menu_item)
    return menu
