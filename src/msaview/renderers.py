import itertools
import math
import re
import string
import sys

import cairo 
import gobject
import gtk
import numpy
import pango
import pangocairo

import action
from color import (Color,
                   ColorSetting,
                   ColormapSetting,
                   Gradient,
                   GradientSetting,
                   RegexColormap,
                   RegexColormapSetting)
from cache import Cache
from component import (Change, 
                       Component, 
                       prop)
import log
from preset import (BoolSetting,
                    ComponentSetting,
                    FloatSetting,
                    FontSetting,
                    RegexSetting,
                    Setting,
                    SettingList,
                    SettingStruct,
                    SimpleSetting,
                    presets)
from options import (BooleanOption,
                     ColorOption, 
                     ComponentListOption,
                     ConfigResidueColormap,
                     ConfigResidueColorMapping,
                     FloatOption,
                     FontOption,
                     GradientOption,
                     GradientPreview,
                     Option,
                     RegexColormapOption,
                     RegexOption,
                     ResidueColormapOption,
                     SimpleOptionConfigDialog,
                     _UNSET)
from plotting import (chequers, 
                      get_view_extents, 
                      outlined_regions,
                      scaled_image, 
                      scaled_image_rectangles, 
                      v_bar,
                      vector_based)
from selection import (Area,
                       Region)

# NOT TODO:
# * Renderers should keep the __hash__ silliness in order to work well with the cache. think for example alpha change and caching.
  
def int_prop(name):
    def get(self):
        return getattr(self, '_' + name)
    def set(self, value):
        return setattr(self, '_' + name, int(value))
    return property(get, set)

class RenderArea(object):
    def __init__(self, x, y, width, height, total_width, total_height):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.total_width = total_width
        self.total_height = total_height
        
    x = int_prop('x')
    y = int_prop('y')
    width = int_prop('width')
    height = int_prop('height')
    total_width = int_prop('total_width')
    total_height = int_prop('total_height')
    
    def __eq__(self, other):
        l = ['x', 'y', 'width', 'height', 'total_width', 'total_height']
        return False not in (getattr(other, s) == getattr(self, s) for s in l)

    def __hash__(self):
        l = ['x', 'y', 'width', 'height', 'total_width', 'total_height']
        return hash(tuple(getattr(self, s) for s in l))        
        
    def __repr__(self):
        return "<RenderArea %s>" % ' '.join("%s:%s" % (s, getattr(self, s)) for s in ['x', 'y', 'width', 'height', 'total_width', 'total_height'])

    @classmethod
    def from_view_area(cls, view, area):
        x = view.hadjustment.value + area.x
        y = view.vadjustment.value + area.y
        width = max(0, min(area.width, view.hadjustment.upper - view.hadjustment.value - area.x)) 
        height = max(0, min(area.height, view.vadjustment.upper - view.vadjustment.value - area.y))
        total_width = view.hadjustment.upper
        total_height = view.vadjustment.upper
        return cls(x, y, width, height, total_width, total_height)

    def item_extents(self, item_width, item_height):
        return (self.item_extents_for_axis(item_width, axis='width'),
                self.item_extents_for_axis(item_height, axis='height'))
    
    def item_extents_for_axis(self, total_items, axis='width'):
        if axis in ['positions', 'width', 'h', 0]:
            position = self.x
            length = self.width
            total_length = self.total_width
        elif axis in ['sequences', 'height', 'v', 1]:
            position = self.y
            length = self.height
            total_length = self.total_height
        else:
            raise ValueError('unknown axis')
        scale = float(total_length) / total_items
        first_item = int(total_items * float(position) / total_length)
        last_item = int(total_items * float(position + length) / total_length)
        items_in_view = min(last_item + 1, total_items) - first_item
        return first_item, items_in_view, scale
    
    def msa_area(self, msa):
        first_pos = int(float(self.x) / self.total_width * len(msa))
        n_pos = int(math.ceil(float(self.x + self.width) / self.total_width * len(msa))) - first_pos
        first_seq = int(float(self.y) / self.total_height * len(msa.sequences))
        n_seq = int(math.ceil(float(self.y + self.height) / self.total_height * len(msa.sequences))) - first_seq
        return Area(Region(first_pos, n_pos), Region(first_seq, n_seq))
        
class Renderer(Component):
    __gproperties__ = dict(
        alpha = (
            gobject.TYPE_FLOAT,
            'alpha',
            'opacity of the rendered image',
            0.0,
            1.0,
            1.0,
            gobject.PARAM_READWRITE))

    alpha = prop('alpha')
    
    def __eq__(self, other):
        if other is self:
            return True
        return (isinstance(other, self.__class__) and
                other.alpha == self.alpha)
    
    def __hash__(self):
        return hash((self.__class__, self.alpha)) 

    def do_set_property(self, pspec, value):
        name = pspec.name.replace('-', '_')
        if name == 'alpha':
            if value != getattr(self, name):
                self.propvalues[name] = value
                self.emit('changed', Change('visualization'))
            return
        Component.do_set_property(self, pspec, value) 

    def get_detail_size(self):
        return 0, 0

    def render(self, cr, area):
        pass
    
    def get_slow_render(self, area):
        return False

    def get_options(self):
        return [FloatOption(self, 'alpha', hint_digits=2)]

    def get_tooltip(self, coord):
        return None

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
        self.msaview_name = view.add(self, name)
        return self.msaview_name

    def from_settings(self, setting):
        Component.from_settings(self, setting)
        self.emit('changed', Change('visualization'))
            
def integrate_ancestor_msa(descendant, ancestor):
    if ancestor.msaview_classname == 'data.msa':
        return ancestor
    msa = descendant.find_ancestor('data.msa')
    if msa is None:
        msa = ancestor.integrate_descendant('data.msa')
        if msa is None:
            raise ValueError('no suitable parent')
    return msa
    
class SolidColor(Renderer):
    __gproperties__ = dict(
        color = (gobject.TYPE_PYOBJECT,
            'color',
            'the color to paint with',
            gobject.PARAM_READWRITE))

    msaview_classname = 'renderer.solidcolor'
    propdefaults = dict(alpha=1.0,
                        color=presets.get_setting('color:white'))

    color = prop('color')
    
    def do_set_property(self, pspec, value):
        name = pspec.name.replace('-', '_')
        if name == 'color':
            if value != getattr(self, name):
                self.propvalues[name] = value
                self.emit('changed', Change('visualization'))
            return
        Renderer.do_set_property(self, pspec, value) 

    def __eq__(self, other):
        if other is self:
            return True
        return (isinstance(other, SolidColor) and 
                other.color == self.color and
                other.alpha == self.alpha and 
                other.parent == self.parent)
    
    def __hash__(self):
        return hash((SolidColor, self.color, self.alpha))

    def render(self, cr, area):
        cr.set_source_rgba(*self.color.rgba)
        cr.rectangle(0, 0, area.width, area.height)
        cr.fill()

    def get_options(self):
        return Renderer.get_options(self) + [ColorOption(self)]

class SolidColorSetting(ComponentSetting):
    component_class = SolidColor
    setting_types = dict(alpha=FloatSetting,
                         color=ColorSetting)

presets.register_component_defaults(SolidColorSetting)
presets.add_preset('renderer.solidcolor:white', SolidColorSetting(frompreset='renderer.solidcolor'))

class FragmentLabels(Renderer):
    msaview_classname = "renderer.devel.fragment_labels"
    def __eq__(self, other):
        if other is self:
            return True
        return isinstance(other, FragmentLabels) and other.alpha == self.alpha
    
    def __hash__(self):
        return hash((FragmentLabels, self.alpha))
    
    def render(self, cr, area):
        cr.set_source_rgba(0, 0, 1, self.alpha)
        cr.new_sub_path()
        cr.arc(area.width/2, area.height/2, min(area.width, area.height)/2, 0, 2*math.pi)
        cr.stroke()
        cr.set_source_rgba(0, 0, 0, self.alpha)
        cr.rectangle(0, 0, area.width, area.height)
        cr.clip_preserve()
        cr.stroke()
        offset_label = str((area.x, area.y))
        w, h = cr.text_extents(offset_label)[2:4]
        cr.move_to(area.width/2 - w/2, area.height/2)
        cr.show_text(offset_label)
        totals_label = str((area.total_width, area.total_height))
        w, h = cr.text_extents(totals_label)[2:4]
        cr.move_to(area.width/2 - w/2, area.height/2 + h)
        cr.show_text(totals_label)

class FragmentLabelsSetting(ComponentSetting):
    component_class = FragmentLabels
presets.register_component_defaults(FragmentLabelsSetting)

class MSARenderer(Renderer):
    """Renderer with basic functionality to react to changes in MSAs."""
    __gproperties__ = dict(
        msa = (gobject.TYPE_PYOBJECT,
            'msa',
            'the msa to visualize',
            gobject.PARAM_READWRITE))
    
    msa = prop('msa')
    
    def __eq__(self, other):
        if other is self:
            return True
        return (isinstance(other, ScaledImage) and 
                other.alpha == self.alpha)
    
    def do_set_property_msa(self, pspec, msa):
        if msa == self.msa:
            return
        self.update_change_handlers(msa=msa)
        self.propvalues.update(msa=msa)
        self.handle_msa_change(msa, Change())
        
    def handle_msa_change(self, msa, change):
        # Override to do something useful.
        pass
        
    def integrate(self, ancestor, name=None):
        self.msaview_name = Renderer.integrate(self, ancestor, name)
        msa = integrate_ancestor_msa(self, ancestor)
        self.msa = msa
        self.handle_msa_change(msa, Change())
        return self.msaview_name 

class ScaledImage(MSARenderer):
    __gproperties__ = dict(
        array = (gobject.TYPE_PYOBJECT,
            'image array',
            'numpy array interface to the msa image',
            gobject.PARAM_READABLE),
        image = (gobject.TYPE_PYOBJECT,
            'msa image',
            'pycairo image, one pixel per residue',
            gobject.PARAM_READWRITE))
    
    array = prop('array')
    image = prop('image')
    
    def __eq__(self, other):
        if other is self:
            return True
        return (isinstance(other, ScaledImage) and 
                other.array == self.array and
                other.alpha == self.alpha)
    
    def do_set_property_image(self, pspec, image):
        if image == self.image:
            return
        array = None
        if image is not None:
            array = numpy.frombuffer(image.get_data(), numpy.uint8)
            array.shape = (image.get_height(), image.get_width(), -1)
        self.propvalues.update(array=array, image=image)
        self.emit('changed', Change('visualization'))
        
    def handle_msa_change(self, msa, change):
        if not change.has_changed('sequences'):
            return
        self.image = self.colorize(msa)
        
    def colorize(self, msa):
        if not msa:
            return None
        width = len(msa) 
        height = len(msa.sequences)
        image = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
        return image
    
    def render(self, cr, area):
        if not self.image:
            return
        if vector_based(cr):
            scaled_image_rectangles(cr, area, self.array, self.alpha)
        else:
            scaled_image(cr, area, self.image, self.alpha)
    
    def get_detail_size(self):
        if not self.image:
            return 0, 0
        return self.image.get_width(), self.image.get_height()
    
class ResidueColors(ScaledImage):
    __gproperties__ = dict(
        colormap = (
            gobject.TYPE_PYOBJECT,
            'colormap',
            'a residue colormap',
            gobject.PARAM_READWRITE),
        unrecognized = (
            gobject.TYPE_PYOBJECT,
            'unrecognized-color',
            'color for letters unrecognized by the colormap',
            gobject.PARAM_READWRITE))

    msaview_classname = 'renderer.msa.residue_colors'
    logger = log.get_logger(msaview_classname)

    colormap = prop('colormap')
    unrecognized = prop('unrecognized')
    propdefaults = dict(alpha=1.0,
                        colormap=presets.get_value('colormap:clustalx'),
                        unrecognized=presets.get_value('color:transparent'))
    
    def __hash__(self):
        return hash((ResidueColors, self.msa, self.colormap, self.unrecognized, self.alpha))
    
    def __eq__(self, other):
        if other is self:
            return True
        return (isinstance(other, ResidueColors) and
                other.msa == self.msa and 
                other.colormap == self.colormap and
                other.unrecognized == self.unrecognized and
                other.alpha == self.alpha)
        
    def do_set_property(self, pspec, value):
        name = pspec.name.replace('-', '_')
        if name in ['colormap', 'unrecognized']:
            if value != getattr(self, name):
                self.propvalues[name] = value
                self.image = self.colorize(self.msa)
            return
        ScaledImage.do_set_property(self, pspec, value) 
    
    @log.trace
    def colorize(self, msa):
        if not msa:
            return None
        image = ScaledImage.colorize(self, msa)
        image.flush()
        array = numpy.frombuffer(image.get_data(), numpy.uint8)
        array.shape = (len(msa.sequences), len(msa), -1)
        colormap = self.colormap or presets.get_value('colormap:clustalx')
        unrecognized = self.unrecognized or Color(0, 0, 0, 0)
        try:
            colormap = colormap.flatten()
        except AttributeError:
            pass
        try:
            import _renderers
        except:
            for y, sequence in enumerate(msa.sequences):
                for x, letter in enumerate(sequence):
                    array[y, x] = colormap.get(letter, unrecognized).array
            image.mark_dirty()
            return image
        _renderers.residue_colors_colorize(array, 
                                           msa.sequence_array, 
                                           colormap,
                                           unrecognized.array)
        image.mark_dirty()
        return image
    
    def get_options(self):
        options = [ResidueColormapOption(self), 
                   ColorOption(self, 'unrecognized')]
        return ScaledImage.get_options(self) + options

class ResidueColorsSetting(ComponentSetting):
    component_class = ResidueColors
    setting_types = dict(alpha=FloatSetting, 
                         colormap=ColormapSetting, 
                         unrecognized=ColorSetting)
        
presets.register_component_defaults(ResidueColorsSetting)

COLORMAP_HIGHLIGHT_UNALIGNED = RegexColormap.from_mappings([
    (r'[.-]+', Color(1.0, 1.0, 1.0)),
    (r'(?<!-)-+(?!-)', Color(25, 127, 229)),
    (r'^[.-]+|[.-]+$', Color(229, 51, 25)),
    (r'[a-z]+', Color.from_str('#1919dddd1919')), #Color(25, 204, 25)),
    (r'[xX]+', Color(.7, 0, .9))])

class RegexColors(ScaledImage):
    __gproperties__ = dict(
        colormap = (
            gobject.TYPE_PYOBJECT,
            'colormap',
            'a regex colormap',
            gobject.PARAM_READWRITE))

    msaview_classname = 'renderer.msa.regex'
    
    propdefaults = dict(alpha=1.0,
                        colormap=presets.get_value('colormap.regex:highlight_unaligned'))
    
    colormap = prop('colormap')

    def __hash__(self):
        return hash((RegexColors, self.msa, self.colormap, self.alpha))
    
    def __eq__(self, other):
        if other is self:
            return True
        return (isinstance(other, self.__class__) and
                other.msa == self.msa and
                other.colormap == self.colormap and
                other.alpha == self.alpha)

    def do_set_property(self, pspec, value):
        name = pspec.name.replace('-', '_')
        if name == 'colormap':
            if value != getattr(self, name):
                self.propvalues[name] = value
                self.image = self.colorize(self.msa)
            return
        ScaledImage.do_set_property(self, pspec, value) 

    def colorize(self, msa):
        if not msa:
            return None
        image = ScaledImage.colorize(self, msa)
        image.flush()
        array = numpy.frombuffer(image.get_data(), numpy.uint8)
        array.shape = (len(msa.sequences), len(msa), -1)
        array[:] = 0
        try:
            colormap = self.colormap.flatten()
        except AttributeError:
            colormap = self.colormap
        for regex, color in colormap.mappings:
            r = re.compile(regex)
            for v, sequence in enumerate(msa.sequences):
                for m in r.finditer(sequence):
                    paint_all = True
                    for group_name in m.groupdict():
                        if group_name.lower().startswith('paint'):
                            array[v, m.start(group_name):m.end(group_name)] = color.array
                            paint_all = False
                    if paint_all:
                        array[v, m.start(0):m.end(0)] = color.array
        image.mark_dirty()
        return image
        
    def render(self, cr, area):
        if not self.colormap:
            return
        ScaledImage.render(self, cr, area) 

    def get_options(self):
        return ScaledImage.get_options(self) + [RegexColormapOption(self)]

class RegexColorsSetting(ComponentSetting):
    component_class = RegexColors
    setting_types = dict(alpha=FloatSetting,
                         colormap=RegexColormapSetting)
    
presets.register_component_defaults(RegexColorsSetting)
presets.add_preset('renderer.msa.regex:highlight_unaligned', RegexColorsSetting(frompreset='renderer.msa.regex'))

class ResidueScale(object):
    def __init__(self, *args, **kw):
        self.mappings = dict(*args, **kw)
        self.settings = None
        
    def __len__(self):
        return len(self.mappings)
    
    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            return False
        return (other is self) or other.mappings == self.mappings
    
    def __hash__(self):
        return reduce(lambda l, r: (l << 1) ^ r, (hash(t) for t in self.mappings.items()), hash(ResidueScale))

    def items(self):
        return self.mappings.items()

    def to_str(self):
        return '/'.join("%s:%s" % t for t in self.mappings.items())

    @classmethod
    def from_str(cls, string):
        return cls.from_mappings((aa, float(value)) for aa, value in (s.split(':') for s in string.split('/')))
    
    @classmethod
    def from_mappings(cls, mappings):
        colormap = cls()
        colormap.mappings.update(mappings)
        return colormap
    
    @classmethod
    def from_settings(cls, setting):
        scale = setting.get_value()
        scale.settings = setting
        return scale
    
    def update(self, *args, **kw):
        self.mappings.update(*args, **kw)

class ResidueValueSetting(SimpleSetting):
    @classmethod
    def from_value(cls, value, frompreset=None, preset_registry=None):
        if not value or frompreset:
            raise ValueError('no residue value specified')
        s = cls(value[1], frompreset, preset_registry)
        s.residue = value[0]
        return s
    
    def parse(self, element):
        SimpleSetting.parse(self, element, attrib_name='value')
        if self.value is not None:
            self.value = float(self.value)
        self.residue = element.attrib.get('residue', None)
        if not self.frompreset:
            if not self.value:
                raise ValueError('no residue value specified')
            if not self.residue:
                raise ValueError('no residue specified')
    
    def encode(self, element):
        Setting.encode(self, element)
        if not self.frompreset:
            if self.value:
                element.attrib['value'] = repr(self.value)
            if self.residue:
                element.attrib['residue'] = self.residue
            
    def get_value(self):
        return (self.residue, self.value)
    
class ResidueScaleSetting(SettingList):
    tag = 'map'
    element_setting_type = ResidueValueSetting
    @classmethod
    def from_value(cls, scale, preset_registry=None):
        if scale.settings:
            return scale.settings
        settings = [cls.element_setting_type.from_value(v, preset_registry) for v in scale.items()]
        return cls(settings)
        
    def get_value(self):
        mappings = []
        if self.frompreset:
            mappings = Setting.get_value(self).items()
        mappings.extend(self.get_specified())
        scale = ResidueScale.from_mappings(mappings)
        if self.name:
            scale.frompreset = self.name
        return scale

    def parse(self, element):
        Setting.parse(self, element)
        self.settings = [self.element_setting_type.from_element(e) for e in element.findall('./' + self.tag)]

presets.register_type('scale', ResidueScaleSetting)

class ConfigResidueValue(ConfigResidueColorMapping):
    def __init__(self, regex, color):
        gtk.HBox.__init__(self)
        self.add_button = self._create_button(gtk.STOCK_ADD, gtk.ICON_SIZE_MENU)
        self.pack_start(self.add_button, expand=False, fill=False)
        if color is None:
            return
        self.key_option = Option(None, None, '', regex, 'residue value mapping (residue)', 'the residue to assign the given value')
        self.key_config = self.key_option.create_config_widget()
        self.key_config.props.max_length = 1
        self.key_config.connect('valid-change', lambda w: self.emit('valid-change'))
        self.pack_start(self.key_config, expand=False)
        self.color_option = FloatOption(default=color, value=color, nick='residue value mapping  (value)', tooltip='the value to assign to the given residue', minimum=-float(sys.maxint), maximum=float(sys.maxint), hint_minimum=-10, hint_maximum=10)
        self.color_config = self.color_option.create_config_widget()
        self.color_config.child_set_property(self.color_config.spinbutton, 'expand', False)
        self.color_config.connect('valid-change', lambda w: self.emit('valid-change'))
        self.pack_start(self.color_config)
        self.remove_button = self._create_button(gtk.STOCK_CANCEL, gtk.ICON_SIZE_MENU)
        self.pack_start(self.remove_button, expand=False, fill=False)

class ConfigResidueScale(ConfigResidueColormap):
    colormap_class = ResidueScale
    mapping_config_class = ConfigResidueValue

class ResidueScaleOption(ResidueColormapOption):
    colormap_class = ResidueScale
    config_class = ConfigResidueScale
    def __init__(self, component=None, propname='scale', default=_UNSET, value=_UNSET, nick=None, tooltip=None):
        ResidueColormapOption.__init__(self, component, propname, default, value, nick, tooltip)


class ResidueScaleColors(ScaledImage):
    __gproperties__ = dict(
        gradient = (
            gobject.TYPE_PYOBJECT,
            'gradient',
            'the colors to use for different values in the residue scale',
            gobject.PARAM_READWRITE),
        scale = (
            gobject.TYPE_PYOBJECT,
            'scale',
            'the residue scale to use',
            gobject.PARAM_READWRITE),
        unrecognized = (
            gobject.TYPE_PYOBJECT,
            'unrecognized',
            'the color to use for residues not described by the residue scale',
            gobject.PARAM_READWRITE))

    msaview_classname = 'renderer.msa.scale'
    
    propdefaults = dict(alpha=1.0,
                        gradient=presets.get_value('gradient:ryg'),
                        scale=ResidueScale(),
                        unrecognized=Color(0, 0, 0, 0))
    
    gradient = prop('gradient')
    scale = prop('scale')
    unrecognized = prop('unrecognized')

    def __hash__(self):
        return hash((ScaledImage, self.msa, self.gradient, self.scale, self.unrecognized, self.alpha))
    
    def __eq__(self, other):
        if other is self:
            return True
        return (isinstance(other, self.__class__) and
                other.msa == self.msa and
                other.gradient == self.gradient and
                other.scale == self.scale and
                other.unrecognized == self.unrecognized and
                other.alpha == self.alpha)

    def do_set_property(self, pspec, value):
        name = pspec.name.replace('-', '_')
        if name in ['gradient', 'scale', 'unrecognized']:
            if value != getattr(self, name):
                self.propvalues[name] = value
                self.image = self.colorize(self.msa)
            return
        ScaledImage.do_set_property(self, pspec, value) 

    def colorize(self, msa):
        if not (msa and self.scale and self.gradient):
            return None
        image = ScaledImage.colorize(self, msa)
        image.flush()
        array = numpy.frombuffer(image.get_data(), numpy.uint8)
        array.shape = (len(msa.sequences), len(msa), -1)
        array[:] = 0
        values = self.scale.mappings.values()
        offset = min(values)
        scale = max(values) - offset 
        colormap = dict((aa.lower(), self.gradient.get_color_from_offset((v - offset)/scale)) for aa, v in self.scale.mappings.items())
        for y, sequence in enumerate(msa.sequences):
            for x, letter in enumerate(sequence):
                array[y, x] = colormap.get(letter.lower(), self.unrecognized).array
        image.mark_dirty()
        return image
        
    def render(self, cr, area):
        if not (self.msa and self.scale and self.gradient):
            return
        ScaledImage.render(self, cr, area) 

    def get_options(self):
        return ScaledImage.get_options(self) + [GradientOption(self), ResidueScaleOption(self), ColorOption(self, 'unrecognized')]

class ResidueScaleColorsSetting(ComponentSetting):
    component_class = ResidueScaleColors
    setting_types = dict(alpha=FloatSetting,
                         gradient=GradientSetting,
                         scale=ResidueScaleSetting,
                         unrecognized=ColorSetting)
    
presets.register_component_defaults(ResidueScaleColorsSetting)

class Label(object):
    def __init__(self, text, font, color=None):
        if color is None:
            color = Color(0, 0, 0)
        self.text = text
        self.font = font
        self.color = color
        
    def __hash__(self):
        return hash((self.text, self.font, self.color))
    
    def __eq__(self, other):
        return other.text == self.text and other.font == self.font and other.color == self.color

# TODO: get rid of the letter cache. It is unnecessay since cairo does such a gosh darned good job atrendering letters quickly anyway.

class MSALetters(MSARenderer):
    __gproperties__ = dict(
        always_show = (
            gobject.TYPE_PYOBJECT,
            'always show',
            'draw letters even though they will overlap into neighboring cells',
            gobject.PARAM_READWRITE),
        color = (
            gobject.TYPE_PYOBJECT,
            'color',
            'color for the letters in the msa',
            gobject.PARAM_READWRITE),
        font = (
            gobject.TYPE_PYOBJECT,
            'msa font',
            'font for the letters in the msa',
            gobject.PARAM_READWRITE))

    msaview_classname = 'renderer.msa.letters'
    logger = log.get_logger(msaview_classname)
        
    propdefaults = dict(alpha=1.0,
                        always_show=False,
                        color=presets.get_value('color:black'),
                        font=presets.get_setting('font:default'))
    def __init__(self):
        MSARenderer.__init__(self)
        self.pango_context = pangocairo.cairo_font_map_get_default().create_context()
        self.cache = Cache()
        self._letter_size = None
        
    always_show = prop('always_show')
    color = prop('color')
    font = prop('font')

    def __hash__(self):
        return hash((MSALetters, self.msa, self.pango_context, self.always_show, self.color, self.font, self.alpha))
    
    def __eq__(self, other):
        if other is self:
            return True
        return (isinstance(other, MSALetters) and
                other.msa == self.msa and
                other.pango_context == self.pango_context and
                other.always_show == self.always_show and
                other.color == self.color and
                other.font == self.font and
                other.alpha == self.alpha)
         
    def do_set_property(self, pspec, value):
        name = pspec.name.replace('-', '_')
        if name in ['always_show', 'color', 'font']:
            if value != getattr(self, name):
                self.propvalues[name] = value
                if name == 'font':
                    self.update_letter_size()
                else:
                    self.emit('changed', Change('visualization'))
            return
        MSARenderer.do_set_property(self, pspec, value) 

    @log.trace
    def handle_msa_change(self, msa, change):
        if not change.has_changed('sequences'):
            return
        self.update_letter_size()

    def update_letter_size(self):
        self._letter_size = self.calculate_letter_size()
        self.emit('changed', Change('visualization'))
        
    def get_detail_size(self):
        if self._letter_size is None:
            return 0, 0
        return self._letter_size[2] * len(self.msa), self._letter_size[3] * len(self.msa.sequences)

    def get_fonts(self):
        """Should return all the fonts that the renderer will use. 
        
        Used to calculate letter size. Override in subclasses that use 
        multiple fonts.
        """        
        return [self.font]

    def calculate_letter_size(self):
        if not self.msa:
            return None
        layout = pango.Layout(self.pango_context)
        log_width = 0
        log_height = 0
        ink_width = 0
        ink_height = 0
        letters = string.letters
        for font in self.get_fonts():
            layout.set_font_description(font)
            for letter in letters:
                # The intricate return values from ...get_pixel_extents():
                #ink, logic = layout.get_line(0).get_pixel_extents()
                #ink_xbearing, ink_ybearing, ink_w, ink_h = ink
                #log_xbearing, log_ybearing, log_w, log_h = logic
                layout.set_text(letter)
                extents = layout.get_line(0).get_pixel_extents()
                log_width = max(log_width, extents[1][2])
                ink_width = max(ink_width, extents[0][2])
                log_height = max(log_height, extents[1][3])
                ink_height = max(ink_height, extents[0][3])
        return log_width, log_height, ink_width, ink_height


    def draw_letter(self, letter):
        layout = pango.Layout(self.pango_context)
        layout.set_font_description(letter.font)
        layout.set_text(letter.text)
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, self._letter_size[0], self._letter_size[1])
        cr = gtk.gdk.CairoContext(cairo.Context(surface))
        # The intricate return values from ...get_pixel_extents():
        #ink, logic = layout.get_line(0).get_pixel_extents()
        #ink_xbearing, ink_ybearing, ink_w, ink_h = ink
        #log_xbearing, log_ybearing, log_w, log_h = logic
        letter_width = layout.get_line(0).get_pixel_extents()[1][2]
        # For debugging:
        #cr.rectangle(0, 0, self._letter_size[0], self._letter_size[1])
        #cr.stroke()
        cr.translate((self._letter_size[0] - letter_width)/2, 0)
        cr.set_source_rgba(*letter.color.rgba)
        cr.show_layout(layout)
        # For debugging:
        #surface.write_to_png('letters/%s.png' % letter.letter)
        return surface

    def get_letter_surface(self, letter):
        try:
            return self.cache[letter]
        except:
            l = self.draw_letter(letter)
            self.cache[letter] = l
            return l
        
    def get_letter(self, seq, pos, letter):
        font = self.get_font(seq, pos, letter)
        color = self.get_color(seq, pos, letter)
        return Label(letter, font, color)
        
    def get_font(self, seq, pos, letter):
        """Override in subclasses that want to vary fonts."""
        return self.font

    def get_color(self, seq, pos, letter):
        """Override in subclasses that want to vary colorization."""
        return self.color
    
    def render(self, cr, area):
        if self._letter_size is None:
            return
        first_pos, n_pos, xscale = get_view_extents(area.x, area.width, area.total_width, len(self.msa))
        first_seq, n_seq, yscale = get_view_extents(area.y, area.height, area.total_height, len(self.msa.sequences))
        if not self.always_show and (xscale < self._letter_size[2] or yscale < self._letter_size[3]):
            return
        cr.rectangle(0, 0, area.width, area.height)
        cr.clip()
        xoffset = xscale/2 - area.x
        yoffset = (yscale - self._letter_size[1])/2 - area.y
        cr.translate(xoffset, yoffset)
        layout = pango.Layout(self.pango_context)
        for seq in range(first_seq, first_seq + n_seq): 
            sequence = self.msa.sequences[seq]
            for pos in range(first_pos, first_pos + n_pos):
                try:
                    aa = sequence[pos]
                except IndexError:
                    continue
                letter = self.get_letter(seq, pos, aa)
                # TODO: clean this up:
                layout.set_font_description(letter.font)
                layout.set_text(letter.text)
                # The intricate return values from ...get_pixel_extents():
                #ink, logic = layout.get_line(0).get_pixel_extents()
                #ink_xbearing, ink_ybearing, ink_w, ink_h = ink
                #log_xbearing, log_ybearing, log_w, log_h = logic
                letter_width = layout.get_line(0).get_pixel_extents()[1][2]
                # For debugging:
                #cr.rectangle(0, 0, self._letter_size[0], self._letter_size[1])
                #cr.stroke()
                cr.move_to(pos * xscale - 0.5 * letter_width, seq * yscale)
                cr.set_source_rgba(*letter.color.with_alpha(self.alpha).rgba)
                cr.show_layout(layout)
                    
    
    def get_slow_render(self, area):
        if not(self.msa):
            return False
        xscale = float(area.total_width) / len(self.msa)
        yscale = float(area.total_height) / len(self.msa.sequences)
        return (self._letter_size is not None and
                (self.always_show or
                 (xscale >= self._letter_size[2] and 
                  yscale >= self._letter_size[3])))

    def get_options(self):
        options = [BooleanOption(self, 'always_show'), 
                   ColorOption(self), 
                   FontOption(self)]
        return Renderer.get_options(self) + options

class MSALettersSetting(ComponentSetting):
    component_class = MSALetters
    setting_types = dict(alpha=FloatSetting,
                         always_show=BoolSetting,
                         color=ColorSetting,
                         font=FontSetting)
    
presets.register_component_defaults(MSALettersSetting)

class TextTransform(object):
    def __init__(self, name, match, format='%(id)s', color=None, font=None, extract=None, disabled=False, tooltip=None, blurb=None):
        if isinstance(match, basestring):
            match = re.compile(match)
        if isinstance(extract, basestring):
            extract = re.compile(extract)
        self.name = name
        self.match = match
        self.format = format
        self.color = color
        self.font = font
        self.extract = extract
        self.disabled = disabled
        self.tooltip = tooltip
        self.blurb = blurb
        
    def __eq__(self, other):
        return (self.name == other.name and
                self.match == other.match and
                self.format == other.format and
                self.color == other.color and
                self.font == other.font and
                self.extract == other.extract and 
                self.disabled == other.diasbled)
        
    def __hash__(self):
        return hash((self.name, self.match, self.format, self.color, self.font, self.extract, self.disabled))
    
    def transform(self, text):
        if not self.disabled:
            m = self.match.search(text)
            if m:
                if self.extract is not None:
                    m = self.extract.search(text)
                text = self.format % m.groupdict()
                return text
        return None 

class NumberTransform(object):
    def __init__(self, name, format="%s", color=None, font=None, disabled=False, tooltip=None, blurb=None):
        self.name = name
        self.format = format
        self.color = color
        self.font = font
        self.disabled = disabled
        self.tooltip = tooltip
        self.blurb = blurb

    def __eq__(self, other):
        return (self.name == other.name and
                self.format == other.format and
                self.color == other.color and
                self.font == other.font and
                self.disabled == other.diasbled)
        
    def __hash__(self):
        return hash((self.name, self.format, self.color, self.font, self.disabled))

    def transform(self, number):
        if not self.disabled:
            return self.format % number
        return None

class PercentageTransform(NumberTransform):
    def transform(self, number):
        if not self.disabled:
            return self.format % (number * 100)
        return None

class TransformList(object):
    def __init__(self, transforms=None):
        if transforms is None:
            transforms = []
        self.transforms = transforms
        
    def __eq__(self, other):
        return self.transforms == other.transforms
    
    def __hash__(self):
        return hash(tuple(t for t in self.transforms))

    def transform(self, data):
        for t in self.transforms:
            tr_text = t.transform(data)
            if tr_text is not None:
                return tr_text
        return str(data)

    def get_transform(self, data):
        for t in self.transforms:
            tr_text = t.transform(data)
            if tr_text is not None:
                return t

# TODO: Label transform settings.

# TODO: get rid of the label cache. It is unnecessay since cairo does such a gosh darned good job at rendering letters quickly anyway.

class Labeler(Renderer):
    __gproperties__ = dict(
        color = (
            gobject.TYPE_PYOBJECT,
            'color',
            'color for the labels',
            gobject.PARAM_READWRITE),
        font = (
            gobject.TYPE_PYOBJECT,
            'label font',
            'font for the labels',
            gobject.PARAM_READWRITE),
        transform_labels = (
            gobject.TYPE_BOOLEAN,
            'transform labels',
            'try to present more human readable labels',
            False,
            gobject.PARAM_READWRITE),
        label_transforms = (
            gobject.TYPE_PYOBJECT,
            'label transforms',
            'transform rules for making labels more human readable',
            gobject.PARAM_READWRITE),
        resize_seqview_to_fit = (
            gobject.TYPE_BOOLEAN,
            'resize seqview to fit',
            'try to resize the containing seqview to fit the labels',
            False,
            gobject.PARAM_READWRITE))

    propdefaults = dict(alpha=1.0,
                        color=presets.get_value('color:black'),
                        font=presets.get_setting('font:default'),
                        transform_labels=False,
                        resize_seqview_to_fit=False)
    
    def __init__(self):
        Renderer.__init__(self)
        self.pango_context = pangocairo.cairo_font_map_get_default().create_context()
        self.cache = Cache()
        self._label_size = None
        self._label_widths = None
        
    color = prop('color')
    font = prop('font')
    transform_labels = prop('transform_labels')
    label_transforms = prop('label_transforms')
    resize_seqview_to_fit = prop('resize_seqview_to_fit')

    def __hash__(self):
        return hash((Labeler, self.pango_context, self.color, self.font, self.transform_labels, self.label_transforms, self._label_size, self.alpha))
    
    def __eq__(self, other):
        if other is self:
            return True
        return (isinstance(other, self.__class__) and
                self.pango_context == other.pango_context and
                self.color == other.color and
                self.font == other.font and
                self.transform_labels == other.transform_labels and
                self.label_transforms == other.label_transforms and
                self.resize_seqview_to_fit == other.resize_seqview_to_fit and
                self._label_size == other._label_size and
                self.alpha == other.alpha)
         
    def do_set_property(self, pspec, value):
        name = pspec.name.replace('-', '_')
        if name in ['color', 'font', 'transform_labels', 'resize_seqview_to_fit', 'label_transforms']:
            if value != getattr(self, name):
                self.propvalues[name] = value
                if name != 'color':
                    self.update_label_size()
                self.emit('changed', Change('visualization'))
            return
        Renderer.do_set_property(self, pspec, value) 

    def do_set_property_resize_seqview_to_fit(self, pspec, resize):
        # TODO: this seqview resize business needs neater implementation.
        self.propvalues[pspec.name.replace('-', '_')] = resize
        if resize and self._label_size:
            seqview = self.find_ancestor('view.seq')
            if seqview:
                seqview.width_request = self._label_size[0] + 2
    
    def update_label_size(self):
        self._label_size, self._label_widths = self.calculate_label_sizes()
        # TODO: this seqview resize business needs neater implementation, for example something like:
        #self.emit('changed', Change('width_request', data=self._label_size[0]))
        if self._label_size and self.resize_seqview_to_fit:
            seqview = self.find_ancestor('view.seq')
            if seqview:
               seqview.width_request = self._label_size[0] + 2
        self.emit('changed', Change('visualization'))
    
    @log.trace    
    def calculate_label_sizes(self):
        data = self.get_data()
        if data is None or not len(data):
            return None, None
        #return (100, 7, 5), [100] * len(data)
        widths = []
        ink_height = 0
        log_height = 0
        layout = pango.Layout(self.pango_context)
        import time
        get_label_time = 0.0
        render_time = 0.0
        t0 = time.time()
        for i, x in enumerate(data):
            t1 = time.time()
            label = self.get_label(i, x)
            t2 = time.time()
            get_label_time += t2 - t1 
            layout.set_font_description(label.font)
            layout.set_text(label.text)
            # The intricate return values from ...get_pixel_extents():
            #ink, logic = layout.get_line(0).get_pixel_extents()
            #ink_xbearing, ink_ybearing, ink_w, ink_h = ink
            #log_xbearing, log_ybearing, log_w, log_h = logic
            ink_extents, log_extents = layout.get_line(0).get_pixel_extents()
            widths.append(ink_extents[2])
            ink_height = max(ink_height, ink_extents[3])
            log_height = max(log_height, log_extents[3])
            render_time += time.time() - t2
        self.logger.debug('get_label_time: %.3fs' % get_label_time)
        self.logger.debug('render_time: %.3fs' % render_time)
        width = max(widths) 
        return (width, log_height, ink_height), widths
        
    def get_detail_size(self):
        if self._label_size is None:
            return 0, 0
        return 0, (self._label_size[2] + 1) * len(self.get_data())

    def draw_label(self, label):
        layout = pango.Layout(self.pango_context)
        layout.set_font_description(label.font)
        layout.set_text(label.text)
        label_width, label_height = layout.get_line(0).get_pixel_extents()[1][2:]
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, label_width, self._label_size[1])
        cr = gtk.gdk.CairoContext(cairo.Context(surface))
        # For debugging:
        #cr.rectangle(0, 0, 0, self._label_height)
        #cr.stroke()
        cr.set_source_rgba(*label.color.rgba)
        cr.show_layout(layout)
        # For debugging:
        #surface.write_to_png('labels/%s.png' % label.text.replace('/', '_')
        return surface

    def get_label_surface(self, label):
        try:
            return self.cache[label]
        except:
            l = self.draw_label(label)
            self.cache[label] = l
            return l
        
    def get_data(self):
        """Override to return something useful."""
    
    def get_label(self, i, data):
        """Override in subclasses that want to do fancy stuff to labels."""
        transform = self.get_transform(i, data)
        text = self.get_text(i, data, transform)
        font = self.get_font(i, data, transform)
        color = self.get_color(i, data, transform)
        return Label(text, font, color)

    def get_transform(self, i, data):
        """Override in subclasses that want to do fancy stuff to labels."""
        if self.transform_labels:
            return self.label_transforms.get_transform(data)
        return None
    
    def get_text(self, i, data, transform):
        """Override in subclasses that want to do fancy stuff to labels."""
        if self.transform_labels and transform:
            return transform.transform(data)
        return str(data)

    def get_font(self, i, data, transform):
        """Override in subclasses that want to use different letter shapes."""
        return self.font

    def get_color(self, i, data, transform):
        """Override in subclasses that want to colorize labels."""
        return self.color

    def render(self, cr, area):
        if self._label_size is None:
            return
        detail = self.get_detail_size()
        if area.total_width < detail[0] or area.total_height < detail[1]:
            return
        data = self.get_data()
        first_label, n_labels, yscale = get_view_extents(area.y, area.height, area.total_height, len(data))
        cr.rectangle(0, 0, area.width, area.height)
        cr.clip()
        yoffset = int(yscale - self._label_size[1])/2 - area.y
        cr.translate(-area.x + 1, yoffset)
        layout = pango.Layout(self.pango_context)
        for i in range(first_label, first_label + n_labels):
            label = self.get_label(i, data[i])
            layout.set_font_description(label.font)
            layout.set_text(label.text)
            #label_width, label_height = layout.get_line(0).get_pixel_extents()[1][2:]
            y = i * yscale
            if not vector_based(cr):
                y = int(y)
            cr.move_to(0, y)
            cr.set_source_rgba(*label.color.with_alpha(self.alpha).rgba)
            cr.show_layout(layout)

    def get_slow_render(self, area):
        detail = self.get_detail_size()
        return (self._label_size is not None and 
                area.total_height >= detail[1])

    def get_options(self):
        l = [ColorOption(self), 
             BooleanOption(self, 'resize_seqview_to_fit'), 
             BooleanOption(self, 'transform_labels'),
             FontOption(self, default=presets.get_value('font:default'))]
        return Renderer.get_options(self) + l

_uniprot_ac_pattern = r'([A-NR-Z][0-9][A-Z][A-Z0-9][A-Z0-9][0-9]|[OPQ][0-9][A-Z0-9][A-Z0-9][A-Z0-9][0-9])'
_swissprot_name_pattern = r'[A-Z0-9]{1,5}'
_uniprot_species_pattern = r'[A-Z0-9]{3,5}' 

ABBREVIATE_KNOWN_ID_FORMATS = TransformList([
    TextTransform(name='sp',
                  match=r'\b(?P<id>%s_%s)\b' % (_swissprot_name_pattern, _uniprot_species_pattern),
                  tooltip='UniProt/Swissprot IDs',
                  blurb='Removes everything except the matching UniProt/Swissprot ID.',
                  color=Color(0,0,.6)),
    TextTransform(name='trembl',
                  match=r'\b(?P<id>%s_%s)\b' % (_uniprot_ac_pattern, _uniprot_species_pattern),
                  tooltip='UniProt/TrEMBL IDs',
                  blurb='Removes everything except the matching UniProt/TrEMBL ID.',
                  color=Color(.6,0,0)),
    TextTransform(name='up',
                  match=r'\b(?P<id>(%s|%s)_%s)\b' % (_swissprot_name_pattern, _uniprot_ac_pattern, _uniprot_species_pattern),
                  tooltip='UniProt IDs',
                  blurb='Removes everything except the matching UniProt ID.'),
    TextTransform(name='up-ac',
                  match=r'\b(?P<id>(%s|%s)_%s)\b' % (_swissprot_name_pattern, _uniprot_ac_pattern, _uniprot_species_pattern),
                  tooltip='UniProt ACs',
                  blurb='Removes everything except the matching UniProt accession number.')])

class SequenceIDLabeler(Labeler):
    __gproperties__ = dict(
        msa = (gobject.TYPE_PYOBJECT,
            'msa',
            'the msa to visualize',
            gobject.PARAM_READWRITE))

    msaview_classname = 'renderer.seq.ids'
    logger = log.get_logger(msaview_classname)
    
    def __init__(self):
        Labeler.__init__(self)
        self.propvalues['label_transforms'] = ABBREVIATE_KNOWN_ID_FORMATS

    msa = prop('msa')
    
    def __hash__(self):
        return hash((self.__class__, self.pango_context, self.color, self.font, self.transform_labels, self.label_transforms, self._label_size, self.alpha))
    
    def __eq__(self, other):
        if other is self:
            return True
        return (isinstance(other, self.__class__) and
                self.pango_context == other.pango_context and
                self.color == other.color and
                self.font == other.font and
                self.transform_labels == other.transform_labels and
                self.label_transforms == other.label_transforms and
                self.resize_seqview_to_fit == other.resize_seqview_to_fit and
                self._label_size == other._label_size and
                self.alpha == other.alpha)
         
    def do_set_property_msa(self, pspec, msa):
        if msa == self.msa:
            return
        self.update_change_handlers(msa=msa)
        self.propvalues.update(msa=msa)
        self.handle_msa_change(msa, Change())

    def handle_msa_change(self, msa, change):
        if not change.has_changed(['sequences', 'ids']):
            return
        self.update_label_size()

    def get_data(self):
        if self.msa:
            return self.msa.ids

    def get_color(self, i, text, transform):
        if transform:
            return transform.color or Color(0, 0, 0)
        return Color(.1, .1, .1)

    def render(self, cr, area):
        if self._label_size is None:
            return
        detail = self.get_detail_size()
        if area.total_height >= detail[1]:
            return Labeler.render(self, cr, area)
        # If we don't have enough space to draw legible labels we can at least do a label sized shading. 
        values = [float(i)/area.total_width for i in self._label_widths]
        first_label, n_labels, yscale = get_view_extents(area.y, area.height, area.total_height, len(self.get_data()))
        cr.rectangle(0, 0, area.width, area.height)
        cr.clip()
        cr.translate(-area.x + 1, 0)
        v_bar(cr, None, None, values, first_label, n_labels, area.y, area.total_width, area.total_height)
        if vector_based(cr):
            cr.set_source_rgba(.85, .85, .85, self.alpha)
        else:
            cr.set_source(chequers((.5, .5, .5, self.alpha), (1, 1, 1, 1), 1))
        cr.fill()

    def integrate(self, ancestor, name=None):
        self.msaview_name = Labeler.integrate(self, ancestor, name)
        msa = integrate_ancestor_msa(self, ancestor)
        self.msa = msa
        return self.msaview_name 
        
    def get_tooltip(self, coord):
        if not self.msa:
            return
        tooltip = "%s %s" % (self.msa.ids[coord.sequence], self.msa.descriptions[coord.sequence] or '')
        return tooltip.replace('<', '&lt;')
        
class SequenceIDLabelerSetting(ComponentSetting):
    component_class = SequenceIDLabeler
    setting_types = dict(alpha=FloatSetting,
                         color=ColorSetting,
                         font=FontSetting,
                         transform_labels=BoolSetting,
                         resize_seqview_to_fit=BoolSetting)

presets.register_component_defaults(SequenceIDLabelerSetting)

class SequenceInformationRenderer(Renderer):
    __gproperties__ = dict(
        color = (
            gobject.TYPE_PYOBJECT,
            'color',
            'how to colorize the sequence features',
            gobject.PARAM_READWRITE),
        feature_map = (
            gobject.TYPE_PYOBJECT,
            'feature_map',
            'sequence features mapped to the msa',
            gobject.PARAM_READWRITE),
        registry = (
            gobject.TYPE_PYOBJECT,
            'registry',
            'the sequence information registry',
            gobject.PARAM_READWRITE)
        )

    propdefaults = dict(alpha=1.0,
                        color=Color(.8, .1, .1))
    def __init__(self):
        Renderer.__init__(self)
        self.category_name = None
        self.image = None
        
    color = prop('color')
    feature_map = prop('feature_map')
    registry = prop('registry')
        
    def do_set_property_registry(self, pspec, value):
        if value != self.registry:
            self.update_change_handlers(registry=value)
            self.propvalues['registry'] = value
            self.handle_registry_change(value, Change())
        
    def do_set_property_feature_map(self, pspec, value):
        if value == self.feature_map:
            return
        self.propvalues['feature_map'] = value
        self.emit('changed', Change('visualization'))

    def handle_registry_change(self, registry, change):
        if change.has_changed('categories'):
            category = registry.get_category(self.category_name)
            connection = self.connections.get('category', None)
            if connection is None or category != connection.source:
                self.update_change_handlers(category=category)
                self.handle_category_change(category, Change())

    def handle_category_change(self, category, change):
        """Override to do something useful."""

presets.add_builtin('gradient:sequence_region_default', 
    Gradient.from_colorstops((0.0, Color(.807, .227, .11)), 
                             (1.0, Color(.90, .725, .141))))

presets.add_builtin('gradient:sequence_features_default', 
    Gradient.from_colorstops((0.00, Color.from_str("#cd391c")),
                             (0.33, Color.from_str("#e5b823")),
                             (0.66, Color.from_str("#23e536")),
                             (1.00, Color.from_str("#232ce5"))))

class SequenceFeatureFilter(object):
    def __init__(self, source=None, name=None, description=None):
        if isinstance(source, str):
            source = re.compile(source, re.IGNORECASE)
        if isinstance(name, str):
            name = re.compile(name, re.IGNORECASE)
        if isinstance(description, str):
            description = re.compile(description, re.IGNORECASE)
        self.source = source
        self.name = name
        self.description = description
        
    def match(self, feature):
        if self.source is not None and not self.source.search(feature.source):
            return False
        if self.name is not None and not self.name.search(feature.name):
            return False
        #print self.description and repr(self.description.pattern), feature.description
        if self.description is not None and not self.description.search(feature.description):
            return False
        return True

class SequenceFeatureFilterSetting(SettingStruct):
    setting_types = dict(
        source=RegexSetting,
        name=RegexSetting,
        description=RegexSetting)
    
    def get_value(self):
        value = SequenceFeatureFilter()
        if self.frompreset:
            v = self.presets.get_value(self.frompreset)
            value.source = v.source
            value.name = v.name
            value.description = v.description
        value.__dict__.update(self.get_specified())
        return value

    @classmethod
    def from_value(cls, value, fromvalue=None, preset_registry=None):
        d = dict(source=value.source, name=value.name, description=value.description)
        settings = dict.fromkeys(cls.setting_types)
        for name, v in d.items():
            settings[name] = cls.setting_types[name].from_value(v, preset_registry=preset_registry)
        return cls(settings, fromvalue, preset_registry) 

class SequenceFeatureColorMapping(object):
    def __init__(self, filter=None, gradient=None, group=False, suppress=False):
        self.filter = filter
        self.gradient = gradient
        self.group = group
        self.suppress = suppress

class SequenceFeatureColorMappingSetting(SettingStruct):
    setting_types = dict(
        filter=SequenceFeatureFilterSetting,
        gradient=GradientSetting,
        group=BoolSetting,
        suppress=BoolSetting)

    def get_value(self):
        value = SequenceFeatureColorMapping()
        if self.frompreset:
            v = self.presets.get_value(self.frompreset)
            value.filter = v.filter
            value.gradient = v.gradient
            value.group = v.group
            value.suppress = v.suppress
        value.__dict__.update(self.get_specified())
        return value

    @classmethod
    def from_value(cls, value, fromvalue=None, preset_registry=None):
        d = dict(filter=value.filter, gradient=value.gradient, group=value.group, suppress=value.suppress)
        settings = dict.fromkeys(cls.setting_types)
        for name, v in d.items():
            settings[name] = cls.setting_types[name].from_value(v, preset_registry=preset_registry)
        return cls(settings, fromvalue, preset_registry) 

class SequenceFeatureColormap(object):
    def __init__(self, mappings=None):
        if mappings is None:
            mappings = []
        self.mappings = mappings
        self.settings = None
        
    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            return False
        return other.mappings == self.mappings
    
    def __hash__(self):
        return hash(tuple(self.mappings))
    
    @classmethod
    def from_mappings(cls, mappings):
        o = cls()
        o.mappings = list(mappings)
        return o
    
class SequenceFeatureColormapSetting(SettingList):
    tag = 'map'
    element_setting_type = SequenceFeatureColorMappingSetting
    @classmethod
    def from_value(cls, colormap, preset_registry=None):
        if colormap.settings:
            return colormap.settings
        settings = [cls.element_setting_type.from_value(v, preset_registry) for v in colormap.mappings]
        return cls(settings)
        
    def get_value(self):
        mappings = []
        if self.frompreset:
            mappings = Setting.get_value(self).mappings
        mappings.extend(self.get_specified())
        colormap = SequenceFeatureColormap.from_mappings(mappings)
        if self.name:
            colormap.frompreset = self.name
        return colormap

presets.register_type('feature_filter', SequenceFeatureFilterSetting)
presets.register_type('feature_colormapping', SequenceFeatureColorMappingSetting)
presets.register_type('colormap.features', SequenceFeatureColormapSetting)

class SequenceFeatureColorMappingConfig(gtk.Table):
    __gsignals__ = dict(
        changed = (
            gobject.SIGNAL_RUN_LAST,
            gobject.TYPE_NONE,
            ())
            )

    @classmethod
    def _create_button(cls, stock, size):
        image = gtk.Image()
        image.set_from_stock(stock, size)
        button = gtk.Button()
        button.add(image)
        button.set_relief(gtk.RELIEF_NONE)
        return button

    def __init__(self, mapping=None):
        gtk.Table.__init__(self, 5, 4)
        source = re.compile('')
        name = re.compile('')
        description = re.compile('')
        if mapping.filter:
            if mapping.filter.source:
                source = mapping.filter.source
            if mapping.filter.name:
                name = mapping.filter.name
            if mapping.filter.description:
                description = mapping.filter.description
        self.source_option = RegexOption(None, None, '', source, 'Filter - source', 'paint features whose source matches this regular expression (if given)')
        self.name_option = RegexOption(None, None, '', name, 'Filter - name', 'paint features whose name matches this regular expression (if given)')
        self.description_option = RegexOption(None, None, '', description, 'Filter - description', 'paint features whose description matches this regular expression (if given)')
        self.gradient_option = GradientOption(None, None, '', mapping.gradient, 'Gradient', 'determines the colors to use for matching features')
        self.group_option = BooleanOption(None, None, '', mapping.group, 'Group:', 'group all matching features and use only the starting color in the gradient')
        self.suppress_option = BooleanOption(None, None, '', mapping.suppress, 'Suppress:', 'suppress all matching features from view')
        
        self.add_button = self._create_button(gtk.STOCK_ADD, gtk.ICON_SIZE_MENU)
        self.gradient_button = gtk.Button()
        self.gradient_button.connect('clicked', self.handle_gradient_button_clicked)
        self.gradient_button.add(GradientPreview(mapping.gradient))
        self.gradient_button.set_relief(gtk.RELIEF_NONE)
        self.remove_button = self._create_button(gtk.STOCK_CANCEL, gtk.ICON_SIZE_MENU)
        self.attach(self.add_button, 0, 1, 0, 1, xoptions=0)
        self.attach(self.gradient_button, 1, 3, 0, 1)
        self.attach(self.remove_button, 3, 4, 0, 1, xoptions=0)

        self.props.column_spacing = 5
        self.source_config = self.source_option.create_config_widget()
        self.source_config.connect_after('changed', lambda w: self.emit('changed'))
        source_label = gtk.Label()
        source_label.set_markup_with_mnemonic('_Source')
        source_label.set_mnemonic_widget(self.source_config)
        self.attach(source_label, 1, 2, 1, 2, xoptions=0)
        self.attach(self.source_config, 2, 3, 1, 2)
        
        self.name_config = self.name_option.create_config_widget()
        self.name_config.connect_after('changed', lambda w: self.emit('changed'))
        name_label = gtk.Label()
        name_label.set_markup_with_mnemonic('_Name')
        name_label.set_mnemonic_widget(self.name_config)
        self.attach(name_label, 1, 2, 2, 3, xoptions=0)
        self.attach(self.name_config, 2, 3, 2, 3)
        
        self.description_config = self.description_option.create_config_widget()
        self.description_config.connect_after('changed', lambda w: self.emit('changed'))
        description_label = gtk.Label()
        description_label.set_markup_with_mnemonic('_Description')
        description_label.set_mnemonic_widget(self.description_config)
        self.attach(description_label, 1, 2, 3, 4, xoptions=0)
        self.attach(self.description_config, 2, 3, 3, 4)
        
        group_config = self.group_option.create_config_widget()
        group_config.connect('changed', lambda w: self.emit('changed'))
        group_config.props.label = '_Group matching features'
        group_config.props.use_underline = True
        self.attach(group_config, 2, 3, 4, 5)

        suppress_config = self.suppress_option.create_config_widget()
        suppress_config.connect('changed', lambda w: self.emit('changed'))
        suppress_config.props.label = 'S_uppress matching features'
        suppress_config.props.use_underline = True
        self.attach(suppress_config, 2, 3, 5, 6)

    valid = property(lambda self: (self.source_config.valid and 
                                   self.name_config.valid and 
                                   self.description_config.valid))

    def handle_gradient_button_clicked(self, button):
        dialog = SimpleOptionConfigDialog(self.gradient_option)
        while True:
            old_gradient = self.gradient_option.value
            response = dialog.run()
            if response != gtk.RESPONSE_APPLY:
                dialog.destroy()
                break
            gradient = dialog.option_config_widget.option.value
            if gradient != old_gradient:
                self.gradient_option.value = gradient
                self.emit('changed')
                self.gradient_button.get_child().set_gradient(gradient)

    def get_mapping(self):
        source = self.source_option.value if self.source_option.value.pattern else None 
        name = self.name_option.value if self.name_option.value.pattern else None 
        description = self.description_option.value if self.description_option.value.pattern else None 
        if source or name or description:
            filter = SequenceFeatureFilter(source, name, description)
        else:
            filter = None
        return SequenceFeatureColorMapping(filter, self.gradient_option.value, self.group_option.value, self.suppress_option.value)

class SequenceFeatureColormapConfig(gtk.ScrolledWindow):
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
        gtk.ScrolledWindow.__init__(self)
        self.option = option
        self.props.hscrollbar_policy = gtk.POLICY_NEVER
        self.props.vscrollbar_policy = gtk.POLICY_ALWAYS
        self.mapping_vbox = gtk.VBox()
        self.mapping_vbox.props.spacing = 10
        self.add_with_viewport(self.mapping_vbox)
        self.revert_value()
    
    valid = property(lambda self: False not in (c.valid for c in self.mapping_vbox.get_children()[:-1]))
    
    def handle_mapping_changed(self, mapping_config):
        i = self.mapping_vbox.get_children().index(mapping_config)
        self.option.value = SequenceFeatureColormap(list(self.option.value.mappings))
        self.option.value.mappings[i] = mapping_config.get_mapping()
        self.emit('changed')

    def handle_add_mapping_clicked(self, button):
        index = 0
        mapping = SequenceFeatureColorMapping()
        if self.option.value.mappings:
            index = max(0, self.mapping_vbox.get_children().index(button.get_parent()) - 1)
            template = self.option.value.mappings[index]
            if template.filter:
                mapping.filter = SequenceFeatureFilter(template.filter.source, template.filter.name, template.filter.description)
            mapping.gradient = Gradient.from_colorstops(*template.gradient.colorstops)
            mapping.group = template.group
        self.option.value = SequenceFeatureColormap(list(self.option.value.mappings))
        self.option.value.mappings.insert(index, mapping)
        self.revert_value()

    def handle_remove_mapping_clicked(self, button):
        mapping_configs = self.mapping_vbox.get_children()
        mapping_config = button.get_parent()
        i = mapping_configs.index(mapping_config)
        self.mapping_vbox.remove(mapping_config)
        mappings = list(self.option.value.mappings)
        del mappings[i]
        self.option.value = SequenceFeatureColormap(mappings)
        self.revert_value()

    def revert_value(self):
        for child in self.mapping_vbox.get_children():
            self.mapping_vbox.remove(child)
        for mapping in self.option.value.mappings:
            mapping_config = SequenceFeatureColorMappingConfig(mapping)
            mapping_config.connect('changed', self.handle_mapping_changed)
            mapping_config.add_button.connect('clicked', self.handle_add_mapping_clicked)
            mapping_config.remove_button.connect('clicked', self.handle_remove_mapping_clicked)
            self.mapping_vbox.pack_start(mapping_config, expand=False)
        add_image = gtk.Image()
        add_image.set_from_stock(gtk.STOCK_ADD, gtk.ICON_SIZE_MENU)
        add_button = gtk.Button()
        add_button.add(add_image)
        add_button.set_relief(gtk.RELIEF_NONE)
        add_hbox = gtk.HBox()
        add_hbox.pack_start(add_button, expand=False)
        add_hbox.pack_start(gtk.Alignment())
        add_button.connect('clicked', self.handle_add_mapping_clicked)
        self.mapping_vbox.pack_start(add_hbox, expand=False)
        self.mapping_vbox.show_all()
        self.emit('changed')

class SequenceFeatureColormapOption(Option):
    def __init__(self, component=None, propname='colormap', default=_UNSET, value=_UNSET, nick=None, tooltip=None):
        if default is _UNSET:
            default = component.propdefaults[propname]
            if isinstance(component, Setting):
                default = default.get_value()
        Option.__init__(self, component, propname, default, value, nick, tooltip)
        self.revert = SequenceFeatureColormap()
        self.revert.mappings = list(self.value.mappings) 
        self.value = SequenceFeatureColormap()
        self.value.mappings = list(self.revert.mappings) 
        
    def parse_str(self, string):
        raise ValueError
        
    def to_str(self, value=_UNSET):
        raise ValueError
        
    def create_config_widget(self):
        w = SequenceFeatureColormapConfig(self)
        w.props.height_request = 200
        return w
    
class SequenceFeatureMap(object):
    def __init__(self, color=None, colormapping=None, features=None, hash=None):
        self.color = color
        self.colormapping = colormapping
        if features is None:
            features = []
        self.features = features
        self.hash = hash

    def __hash__(self):
        if not self.is_frozen():
            raise ValueError('cannot hash unfrozen feature map')
        return self.hash
    
    def sort(self):
        self.features.sort(key=lambda f: (f.sequence_index, f.region.start))
        
    def freeze(self):
        self.features = tuple(self.features)
        self.hash = hash((self.color, self.features))
        
    def is_frozen(self):
        return self.hash is not None
    
    def get_features(self, coord):
        features = []
        for feature in self.features:
            if feature.sequence_index > coord.sequence:
                break
            if feature.sequence_index == coord.sequence and coord.position in feature.mapping:
                features.append(feature)
        return features

class BasicSequenceFeatureRenderer(Renderer):
    """Renderer with basic functionality to react to changes in sequence features."""
    __gproperties__ = dict(
        features = (gobject.TYPE_PYOBJECT,
            'features',
            'the sequence feature registry to visualize',
            gobject.PARAM_READWRITE),
        feature_map = (gobject.TYPE_PYOBJECT,
            'feature_map',
            'what colors to paint where',
            gobject.PARAM_READWRITE))

    features = prop('features')
    feature_map = prop('feature_map')

    def __eq__(self, other):
        if other is self:
            return True
        return (isinstance(other, self.__class__) and 
                other.alpha == self.alpha and
                other.feature_map == self.feature_map)

    def __hash__(self):
        return hash((self.__class__, self.alpha, self.feature_map))
    
    def do_set_property_features(self, pspec, features):
        if features == self.features:
            return
        self.update_change_handlers(features=features)
        self.propvalues.update(features=features)
        self.handle_features_change(features, Change())
        
    def do_set_property_feature_map(self, pspec, feature_map):
        if feature_map == self.feature_map:
            return
        self.propvalues.update(feature_map=feature_map)
        self.emit('changed', Change('visualization'))
        
    def handle_features_change(self, features, change):
        self.feature_map = self.colorize(features)
        
    def colorize(self, features):
        # Override to return a feature map that makes sense.
        return None
    
    def render(self, cr, area):
        # Override to do something useful.
        if self.feature_map is None:
            return
    
    def get_actions(self, coord=None):
        return Renderer.get_actions(self, coord) + action.get_applicable(self.features, coord)
    
    def integrate(self, ancestor, name=None):
        self.msaview_name = Renderer.integrate(self, ancestor, name)
        msa = integrate_ancestor_msa(self, ancestor)
        # unparent if sequence_features are unparented.
        msa.features.connect('descendant_removed', lambda f, d: f is d and self.unparent())
        self.features = msa.features
        return self.msaview_name 

class SequenceFeatureRenderer(BasicSequenceFeatureRenderer):
    __gproperties__ = dict(
        cell_size = (
            gobject.TYPE_PYOBJECT,
            'cell_size',
            'minimum open area within cells for showing outlines',
            gobject.PARAM_READWRITE),
        colormap = (
            gobject.TYPE_PYOBJECT,
            'colormap',
            'colors for known region types',
            gobject.PARAM_READWRITE),
        linewidth = (
            gobject.TYPE_INT,
            'linewidth',
            'width of region outlines',
            0,
            100000,
            3,
            gobject.PARAM_READWRITE),
        outline_alpha = (
            gobject.TYPE_BOOLEAN,
            'outline_alpha',
            'use alpha blending for region outlines',
            False,
            gobject.PARAM_READWRITE),
        )
    
    msaview_classname = 'renderer.msa.features'
    propdefaults = dict(alpha=0.6,
                        colormap=SequenceFeatureColormap(),
                        linewidth=2,
                        outline_alpha=False)
    
    def __init__(self):
        BasicSequenceFeatureRenderer.__init__(self)
        self.image = None
        self.array = None
        # TODO: Find better way of finding letter size and put here.
        self.propvalues['cell_size'] = (-1, -1)
    
    def __eq__(self, other):
        return (isinstance(other, self.__class__) and
                other.alpha == self.alpha and
                other.cell_size == self.cell_size and
                other.linewidth == self.linewidth and
                other.outline_alpha == self.outline_alpha and
                other.colormap == self.colormap and
                other.feature_map == self.feature_map)
        
    def __hash__(self):
        return hash((self.__class__, self.alpha, self.cell_size, self.linewidth, self.outline_alpha, self.feature_map))
    
    cell_size = prop('cell_size')
    colormap = prop('colormap')
    linewidth = prop('linewidth')
    outline_alpha = prop('outline_alpha')
    
    def do_set_property(self, pspec, value):
        name = pspec.name.replace('-', '_')
        if name in ['colormap', 'linewidth', 'outline_alpha']:
            if value != getattr(self, name):
                self.propvalues[name] = value
                self.image, self.feature_map = self.colorize(self.features)
                self.emit('changed', Change('visualization'))
            return
        BasicSequenceFeatureRenderer.do_set_property(self, pspec, value) 

    def get_options(self):
        options = [SequenceFeatureColormapOption(self), BooleanOption(self, 'outline_alpha'), FloatOption(self, 'linewidth')]
        return BasicSequenceFeatureRenderer.get_options(self) + options  

    def handle_features_change(self, features, change):
        self.image, self.feature_map = self.colorize(features)

    def colorize(self, feature_registry):
        if not feature_registry.features or not self.colormap.mappings:
            return None, None
        # Match features to colormap rules and determine number of needed gradient generated colors
        features = [[[]] for mapping in self.colormap.mappings]
        for feature in itertools.chain(*feature_registry.features):
            i = len(self.colormap.mappings)
            for rule in reversed(self.colormap.mappings):
                i -= 1
                if rule.filter and not rule.filter.match(feature):
                    continue
                if rule.suppress:
                    break
                if rule.group:
                    features[i][0].append(feature)
                else:
                    for feature_list in features[i]:
                        if not feature_list or feature.equal(feature_list[0]):
                            feature_list.append(feature)
                            break
                    else:
                        features[i].append([feature])
                break
        # Finalize colors and draw order, and build feature maps
        feature_maps = []
        for i, matching_feature_lists in enumerate(features):
            if not matching_feature_lists[0]:
                continue
            colormapping = self.colormap.mappings[i]
            last_step = float(len(matching_feature_lists)) - 1
            for color_step, feature_list in enumerate(matching_feature_lists):
                offset = color_step / last_step if last_step else 0 
                color = colormapping.gradient.get_color_from_offset(offset)
                feature_maps.append(SequenceFeatureMap(color, colormapping, feature_list))
        for feature_map in feature_maps:
            feature_map.sort()
            feature_map.freeze()
        feature_maps = tuple(feature_maps)
        # Colorize image
        width = len(feature_registry.msa)
        height = len(feature_registry.msa.sequences)
        image = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
        image.flush()
        array = numpy.frombuffer(image.get_data(), dtype=numpy.uint8)
        array.shape = (height, width, -1)
        for feature_map in feature_maps:
            for feature in feature_map.features:
                array[feature.sequence_index, feature.mapping.start:feature.mapping.start+feature.mapping.length] = feature_map.color.array
        image.mark_dirty()
        return image, feature_maps
        
    def get_detail_size(self):
        if self.image is None:
            return 0, 0
        cell_size = [(i if i >= 0 else 2 * self.linewidth) for i in self.cell_size]
        return ((cell_size[0] + self.linewidth * 2) * len(self.features.msa), 
                (cell_size[1] + self.linewidth * 2) * len(self.features.msa.sequences))

    def render(self, cr, area):
        if not self.image:
            return 
        detail = self.get_detail_size()
        if area.total_width < detail[0] or area.total_height < detail[1]:
            scaled_image(cr, area, self.image, self.alpha)
        else:
            for feature_map in self.feature_map:
                c = feature_map.color
                if self.outline_alpha:
                    c = feature_map.color.with_alpha(self.alpha)
                outlined_regions(cr, area, len(self.features.msa), len(self.features.msa.sequences), feature_map.features, self.linewidth, c, self.alpha, False)

    def get_tooltip(self, coord):
        if not self.feature_map:
            return
        descriptions = []
        for map in self.feature_map:
            for feature in map.features:
                if feature.sequence_index < coord.sequence:
                    continue
                if feature.sequence_index > coord.sequence or feature.mapping.start > coord.position:
                    break
                if coord.position >= feature.mapping.start + feature.mapping.length:
                    continue
                descriptions.append(feature.to_markup(map.color))
        if descriptions:
            return 'Features: ' + ', '.join(descriptions)

class SequenceFeatureRendererSetting(ComponentSetting):
    component_class = SequenceFeatureRenderer
    setting_types = dict(alpha=FloatSetting,
                         outline_alpha=BoolSetting,
                         colormap=SequenceFeatureColormapSetting,
                         linewidth=FloatSetting)

presets.register_component_defaults(SequenceFeatureRendererSetting)

class SequenceFeatureSummaryBlob(object):
    def __init__(self, color=None, region=None, colormapping=None, features=None, hash=None):
        self.color = color
        self.region = region
        self.colormapping = colormapping
        self.features = features
        self.hash = hash
        
    def __hash__(self):
        if self.hash is None:
            raise ValueError('cannot hash unfrozen blob')
        return self.hash
    
    def add_feature(self, feature):
        self.region.merge(feature.mapping)
        self.features.append(feature)

    def merge(self, blob):
        self.region.merge(blob.region)
        self.features.extend(blob.features)

    def sort(self):
        self.features.sort(key=lambda f: (f.sequence_index, f.region.start))
    
    def freeze(self):
        self.features = tuple(self.features)
        self.hash = hash((SequenceFeatureSummaryBlob, self.color, self.region, self.colormapping, self.features))

    def is_frozen(self):
        return self.hash is not None
    
    def to_str(self):
        f = self.features[0]
        string = "%s %s-%s" % (f.name, self.region.start + 1, self.region.start + self.region.length)
        if f.description:
            string += " (%s)" % f.description
        return string
    
    def to_markup(self):
        template = "<span foreground=%r weight='bold'>%s</span> %s-%s"
        f = self.features[0]
        markup = template % (self.color.to_str(), f.name.replace('<', '&lt;'), self.region.start + 1, self.region.start + self.region.length)
        if f.description:
            markup += " (%s)" % f.description
        return markup

class SequenceFeatureSummary(object):
    def __init__(self, tracks=None, hash=None):
        if tracks is None:
            tracks = []
        self.tracks = tracks
        self.hash = hash

    def __hash__(self):
        if not self.is_frozen():
            raise ValueError('cannot hash unfrozen feature map')
        return self.hash
    
    def __nonzero__(self):
        return bool(self.tracks)
    
    def add_blob(self, blob):
        for track in self.tracks:
            if blob.region.start + blob.region.length <= track[0].region.start:
                track.insert(0, blob)
                return
            for i in range(len(track)):
                if blob.region.start < track[i].region.start + track[i].region.length:
                    continue
                if (i == len(track) - 1 or
                    blob.region.start + blob.region.length <= track[i + 1].region.start):
                    track.insert(i + 1, blob)
                    return
        self.tracks.append([blob])
    
    def freeze(self):
        self.tracks = tuple(tuple(t) for t in self.tracks)
        self.hash = hash(self.tracks)
        
    def is_frozen(self):
        return self.hash is not None
    
    def get_blob(self, coord):
        i = int(float(coord.y) / coord.total_height * len(self.tracks))
        for blob in self.tracks[i]:
            if blob.region.start > coord.position:
                return
            if coord.position in blob.region:
                return blob

class SequenceFeatureSummaryRenderer(BasicSequenceFeatureRenderer):
    __gproperties__ = dict(
        colormap = (
            gobject.TYPE_PYOBJECT,
            'colormap',
            'colors for known region types',
            gobject.PARAM_READWRITE),
        )
    
    msaview_classname = 'renderer.pos.features'
    propdefaults = dict(alpha=1.0,
                        colormap=SequenceFeatureColormap()
                        )
    
    def __eq__(self, other):
        return (isinstance(other, self.__class__) and
                other.alpha == self.alpha and
                other.colormap == self.colormap and
                other.feature_map == self.feature_map)
        
    colormap = prop('colormap')
    feature_map = prop('feature_map')
    gradient = prop('gradient')
    
    def do_set_property(self, pspec, value):
        name = pspec.name.replace('-', '_')
        if name in ['colormap']:
            if value != getattr(self, name):
                self.propvalues[name] = value
                self.feature_map = self.colorize(self.features)
            return
        BasicSequenceFeatureRenderer.do_set_property(self, pspec, value) 

    def get_options(self):
        options = [SequenceFeatureColormapOption(self)]
        return BasicSequenceFeatureRenderer.get_options(self) + options  

    def colorize(self, feature_registry):
        if not feature_registry.features or not self.colormap.mappings:
            return None
        def update_blob_list(blob_list, feature):
            for i in range(len(blob_list)):
                blob = blob_list[i]
                if feature.mapping.start + feature.mapping.length <= blob.region.start:
                    region = Region(feature.mapping.start, feature.mapping.length)
                    blob_list.insert(i, SequenceFeatureSummaryBlob(region=region, features=[feature]))
                    return
                if blob.region.overlap(feature.mapping):
                    blob.add_feature(feature)
                    if i < len(blob_list) - 1:
                        if blob.region.overlap(blob_list[i + 1].region):
                            blob.merge(blob_list.pop(i + 1))
                    return
            region = Region(feature.mapping.start, feature.mapping.length)
            blob_list.append(SequenceFeatureSummaryBlob(region=region, features=[feature]))
        # Create blobs according to colormap rules and determine number of needed gradient generated colors
        mapping_blob_lists = [[[]] for mapping in self.colormap.mappings]
        for feature in itertools.chain(*feature_registry.features):
            i = len(self.colormap.mappings)
            for rule in reversed(self.colormap.mappings):
                i -= 1
                if rule.filter and not rule.filter.match(feature):
                    continue
                if rule.suppress:
                    break
                if rule.group:
                    update_blob_list(mapping_blob_lists[i][0], feature)
                    break
                else:
                    for blob_list in mapping_blob_lists[i]:
                        if not blob_list or feature.equal(blob_list[0].features[0]):
                            update_blob_list(blob_list, feature)
                            break
                    else:
                        new_blob_list = []
                        update_blob_list(new_blob_list, feature)
                        mapping_blob_lists[i].append(new_blob_list)
                break
        # Finalize colors and pack blobs into tracks
        feature_map = SequenceFeatureSummary()
        for i, rule in enumerate(self.colormap.mappings):
            last_step = float(len(mapping_blob_lists[i])) - 1
            for color_step, blob_list in enumerate(mapping_blob_lists[i]):
                offset = color_step / last_step if last_step else 0 
                color = rule.gradient.get_color_from_offset(offset)
                for blob in blob_list:
                    blob.color = color
                    blob.colormapping = rule
                    blob.sort()
                    blob.freeze()
                    feature_map.add_blob(blob)
        feature_map.freeze()
        return feature_map

    def get_detail_size(self):
        if not self.feature_map:
            return 0, 0
        return (len(self.features.msa), 0)

    def render(self, cr, area):
        if not self.feature_map:
            return 
        visible_region = area.msa_area(self.features.msa).positions
        track_height = min(20, max(2, area.total_height / len(self.feature_map.tracks) - len(self.feature_map.tracks)))
        for i, track in enumerate(self.feature_map.tracks):
            y = round(float(i) / len(self.feature_map.tracks) * area.total_height)
            for blob in track:
                if blob.region.overlap(visible_region):
                    x = float(blob.region.start)/len(self.features.msa) * area.total_width - area.x 
                    blob_width = float(blob.region.length)/len(self.features.msa) * area.total_width
                    if blob_width < track_height:
                        cr.rectangle(x, y, blob_width, track_height)
                    else:
                        cr.new_sub_path()
                        r = 0.5*track_height
                        cr.arc(x + r, y + r, r, math.pi/2, 3 * math.pi/2)
                        cr.arc(x + blob_width - r, y + r, r, 3 * math.pi/2, math.pi/2)
                        cr.close_path()
                cr.set_source_rgba(*blob.color.with_alpha(self.alpha).rgba)
                cr.fill()

    def get_tooltip(self, coord):
        if not self.feature_map:
            return
        blob = self.feature_map.get_blob(coord)
        if blob:
            return blob.to_markup()

class SequenceFeatureSummaryRendererSetting(ComponentSetting):
    component_class = SequenceFeatureSummaryRenderer
    setting_types = dict(alpha=FloatSetting,
                         colormap=SequenceFeatureColormapSetting)

presets.register_component_defaults(SequenceFeatureSummaryRendererSetting)

class FeatureAction(action.Action):
    @classmethod
    def applicable(cls, target, coord=None):
        if target.msaview_classname != 'renderer.msa.features':
            return
        if not (coord and target.feature_map):
            return
        actions = []
        for feature_map in target.feature_map: 
            for feature in feature_map.get_features(coord):
                a = cls(target, coord)
                a.params['feature'] = feature
                a.path = list(cls.path)
                a.path[1] = feature.to_str()
                actions.append(a)
        return actions or None

class RemoveFeature(FeatureAction):
    action_name = 'remove-feature'
    path = ['Features', None, 'Remove']
    tooltip = 'Remove the sequence feature.' 
    
    def run(self):
        self.target.features.remove_features(self.params['feature'])

action.register_action(RemoveFeature)

class SelectFeatureRegion(FeatureAction):
    action_name = 'select-feature-region'
    path = ['Features', None, 'Select region']
    tooltip = 'Add the corresponding sequence region to the selection.' 
    
    def run(self):
        feature = self.params['feature']
        region = Region(feature.mapping.start, feature.mapping.length)
        self.target.features.msa.selection.positions.incorporate(region)

action.register_action(SelectFeatureRegion)

class SelectFeature(FeatureAction):
    action_name = 'select-feature'
    path = ['Features', None, 'Select feature']
    tooltip = 'Area select the corresponding feature.' 
    
    def run(self):
        feature = self.params['feature']
        area = Area(Region(feature.mapping.start, feature.mapping.length), Region(feature.sequence_index, 1))
        self.target.features.msa.selection.areas.add(area)

action.register_action(SelectFeature)

class SimilarFeatureAction(action.Action):
    @classmethod
    def applicable(cls, target, coord=None):
        if target.msaview_classname != 'renderer.msa.features':
            return
        if not (coord and target.feature_map):
            return
        actions = []
        for feature_map in target.feature_map: 
            for feature in feature_map.get_features(coord):
                a = cls(target, coord)
                a.params['feature_map'] = feature_map
                a.path = list(cls.path)
                a.path[1] = feature.to_str()
                actions.append(a)
        return actions or None

class FeatureRemoveSimilar(SimilarFeatureAction):
    action_name = 'remove-similar-features'
    path = ['Features', None, 'Remove similar']
    tooltip = 'Remove all similar features.' 
    
    def run(self):
        self.target.features.msa.remove_features(self.params['feature_map'].features)

action.register_action(FeatureRemoveSimilar)

class FeatureSelectSimilar(SimilarFeatureAction):
    action_name = 'feature-select-similar'
    path = ['Features', None, 'Select similar']
    tooltip = 'Area select all similar features.' 
    
    def run(self):
        areas = []
        for feature in self.params['feature_map'].features:
            areas.append(Area(Region(feature.mapping.start, feature.mapping.length), Region(feature.sequence_index, 1)))
        self.target.features.msa.selection.areas.add(areas)

action.register_action(FeatureSelectSimilar)

class FeatureSelectSimilarRegions(SimilarFeatureAction):
    action_name = 'feature-select-similar-regions'
    path = ['Features', None, 'Select similar regions']
    tooltip = 'Area select all similar features.' 

    def run(self):
        regions = []
        for feature in self.params['feature_map'].features:
            regions.append(Region(feature.mapping.start, feature.mapping.length))
        self.target.features.msa.selection.positions.add(regions)

action.register_action(FeatureSelectSimilarRegions)

class FeatureSummaryAction(action.Action):
    @classmethod
    def applicable(cls, target, coord=None):
        if target.msaview_classname != 'renderer.pos.features':
            return
        if not (coord and target.feature_map):
            return
        blob = target.feature_map.get_blob(coord)
        if not blob:
            return
        a = cls(target, coord)
        a.params['blob'] = blob
        a.path = list(cls.path)
        a.path[1] = blob.to_str()
        return a
    
class RemoveFeatureSummaryFeatures(FeatureSummaryAction):
    action_name = 'feature-summary-remove-features'
    path = ['Features', None, 'Remove features']
    tooltip = 'Remove the corresponding sequence features.' 
    
    def run(self):
        self.target.features.remove_features(self.params['blob'].features)

action.register_action(RemoveFeatureSummaryFeatures)

class FeatureSummarySelection(FeatureSummaryAction):
    action_name = 'feature-summary-select-features'
    path = ['Features', None, 'Select features']
    tooltip = 'Add the corresponding sequence features to the selection.' 
    
    def run(self):
        blob = self.params['blob']
        areas = []
        for f in blob.features:
            areas.append(Area(Region(f.mapping.start, f.mapping.length), Region(f.sequence_index, 1)))
        self.target.features.msa.selection.areas.add(areas)

action.register_action(FeatureSummarySelection)

class SelectFeatureSummaryRegion(FeatureSummaryAction):
    action_name = 'feature-summary-select-region'
    path = ['Features', None, 'Select region']
    tooltip = 'Add the feature summary region to the selection' 
    
    def run(self):
        blob = self.params['blob']
        self.target.features.msa.selection.positions.add_region(blob.region.start, blob.region.length)

action.register_action(SelectFeatureSummaryRegion)

class RemoveSimilarFeatureSummaryFeatures(FeatureSummaryAction):
    action_name = 'feature-summary-remove-similar'
    path = ['Features', None, 'Remove similar features']
    tooltip = 'Remove all similar sequence features' 
    
    def get_blobs(self):
        colormapping = self.params['blob'].colormapping
        example = self.params['blob'].features[0]
        def colormapping_matches(blob):
            return blob.colormapping == colormapping
        def annotation_matches(blob):
            return blob.features[0].equal(example)
        test = annotation_matches
        if colormapping.group:
            test = colormapping_matches
        blobs = []
        for track in self.target.feature_map.tracks:
            for blob in track:
                if test(blob):
                    blobs.append(blob)
        return blobs
    
    def run(self):
        features = []
        for blob in self.get_blobs():
            features.extend(blob.features)
        self.target.features.remove_features(features)

action.register_action(RemoveSimilarFeatureSummaryFeatures)

class SelectSimilarFeatureSummaryRegions(RemoveSimilarFeatureSummaryFeatures):
    action_name = 'feature-summary-select-similar-regions'
    path = ['Features', None, 'Select similar regions']
    tooltip = 'Add all similar feature summaries to the selection' 
    
    def run(self):
        regions = [Region(blob.region.start, blob.region.length) for blob in self.get_blobs()]
        self.target.features.msa.selection.positions.add(regions)

action.register_action(SelectSimilarFeatureSummaryRegions)

class SelectMatchingFeatureSummaryFeatures(FeatureSummarySelection):
    action_name = 'feature-summary-select-all-features'
    path = ['Features', None, 'Select all similar features']
    tooltip = 'Add all similar features to the selection' 
    
    def run(self):
        colormapping = self.params['blob'].colormapping
        example = self.params['blob'].features[0]
        def colormapping_matches(blob):
            return blob.colormapping == colormapping
        def annotation_matches(blob):
            return blob.features[0].equal(example)
        test = annotation_matches
        if colormapping.group:
            test = colormapping_matches
        areas = []
        for track in self.target.feature_map.tracks:
            for blob in track:
                if not test(blob):
                    continue
                for f in blob.features:
                    areas.append(Area(Region(f.mapping.start, f.mapping.length), Region(f.sequence_index, 1)))
        self.target.features.msa.selection.areas.add(areas)

action.register_action(SelectMatchingFeatureSummaryFeatures)

def get_ticks(start, items_in_view, tick_hint=9):
    magnitude = max(1, 10 ** int(math.log10(items_in_view / tick_hint)))
    target_step = items_in_view / tick_hint / magnitude
    for step in [1, 2, 5, 10]:
        scaled_step = step * magnitude
        if scaled_step * tick_hint > items_in_view:
            break
    first = scaled_step * int(math.ceil(float(start) / scaled_step))
    if first == int(start):
        first += scaled_step
    stop = scaled_step * int(divmod(start + items_in_view, scaled_step)[0] + 1)
    return first, stop, scaled_step

class RendererStack(Component):
    __gproperties__ = dict(
        renderers = (
            gobject.TYPE_PYOBJECT,
            'renderers',
            'the renderers that will be drawn on top of each other',
            gobject.PARAM_READWRITE))
    
    def __init__(self, renderers=None):
        Component.__init__(self)
        if renderers is None:
            renderers = []
        self.renderers = renderers
    
    renderers = prop('renderers')
        
    def __eq__(self, other):
        return (isinstance(other, self.__class__) and
                other.renderers == self.renderers)
     
    def __getitem__(self, index):
        return self.renderers[index]
    
    def __iter__(self):
        return iter(self.renderers)
    
    def __len__(self):
        return len(self.renderers)
    
    def __hash__(self):
        r = reduce(lambda l, r: (l << 2) ^ r, (hash(t) for t in enumerate(self.renderers)), hash(self.__class__))
        return r
    
    def render(self, cr, area):
        for r in self.renderers:
            cr.save()
            r.render(cr, area)
            cr.restore()
            
    def get_detail_size(self):
        sizes = []
        for r in self.renderers:
            size = r.get_detail_size()
            if size:
                sizes.append(size)
        return tuple(max(l) for l in zip(*sizes)) or (0, 0)

    def get_slow_render(self, area):
        return [True for r in self.renderers if r.get_slow_render(area)]

    def get_options(self):
        return [ComponentListOption(self, 'renderers')]
