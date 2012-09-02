import re

import cairo
import gtk
import numpy

from preset import (Setting, 
                    SettingList, 
                    SimpleSetting,
                    presets)

class Color(object):
    def __init__(self, r, g, b, a=1.0):
        r, g, b, a = [int(n)/255.0 if n > 1 else int(n*255.0)/255.0 for n in [r, g, b, a]]
        self.rgba = [r, g, b, a]
        self.array = numpy.array([int(n*255) for n in [b, g, r, a]], numpy.uint8)
        self.r = r
        self.g = g
        self.b = b
        self.a = a
        self.frompreset = None
    
    def __eq__(self, other):
        return isinstance(other, Color) and (self.array == other.array).all()

    def __repr__(self):
        words = object.__repr__(self).split()
        words.insert(2, self.to_str())
        return ' '.join(words)
    
    @classmethod
    def from_str(cls, string):
        alpha = 1.0
        if ':' in string: 
            string, alpha = string.split(':')
            if string.startswith('#'):
                if not len(alpha) == (len(string) - 1)/3:
                    raise ValueError('alpha channel depth must be equal to the rgb channels')
                alpha = int(alpha, 16) / (2.0 ** (len(alpha) * 4) - 1)
            else:
                alpha = float(alpha)
        c = gtk.gdk.color_parse(string)
        return cls.from_gdk_color(c, alpha)

    @classmethod
    def from_settings(cls, setting):
        return setting.get_value()

    @classmethod
    def from_gdk_color(cls, c, alpha=1.0):
        n = 65535.0
        return cls(c.red/n, c.green/n, c.blue/n, alpha)

    def with_alpha(self, alpha):
        r, g, b, a = self.rgba
        return Color(r, g, b, a * alpha)
    
    def blend(self, amount, color):
        args = [v + (v2 - v) * amount for v, v2 in zip(self.rgba, color.rgba)]
        return Color(*args)
    
    def _color_to_str(self):
        i = 65535
        args = [int(n * i) for n in self.rgba[:-1]]
        s = gtk.gdk.Color(*args).to_string()
        return s[:3] + s[5:7] + s[9:11]
    
    def _alpha_to_str(self):
        if self.a == 1.0:
            return ''
        return ':%02x' % (self.a * 255)
    
    def to_str(self):
        return self._color_to_str() + self._alpha_to_str()

    def to_gdk_color_and_alpha(self):
        alpha = int(self.a * 65535)
        c = gtk.gdk.Color(*[int(n*65535) for n in self.rgba[:-1]]) 
        return c, alpha

    def __hash__(self):
        return hash((Color, tuple(self.rgba)))

class ColorSetting(SimpleSetting):
    @classmethod
    def from_value(cls, value, frompreset=None, preset_registry=None):
        if not value or frompreset:
            raise ValueError('no color specified')
        return cls(value.to_str(), frompreset, preset_registry)
    
    def parse(self, element):
        SimpleSetting.parse(self, element, attrib_name='color')
        if not self.value and not self.frompreset:
            raise ValueError('no color specified')
    
    def encode(self, element):
        Setting.encode(self, element)
        if self.value and not self.frompreset:
            element.attrib['color'] = self.value
            
    def get_value(self):
        if self.frompreset:
            color = self.presets.get_value(self.frompreset)
        if self.value:
            color = Color.from_str(self.value)
        if self.name:
            color.frompreset = self.name 
        return color

COLOR_TRANSPARENT = Color(0, 0, 0, 0)
COLOR_BLACK = Color(0, 0, 0)
COLOR_WHITE = Color(1, 1, 1)

COLOR_TRANSPARENT_ARRAY = COLOR_TRANSPARENT.array
COLOR_BLACK_ARRAY = COLOR_BLACK.array
COLOR_WHITE_ARRAY = COLOR_WHITE.array
    
presets.register_type('color', ColorSetting)
presets.add_builtin('color:black', COLOR_BLACK)
presets.add_builtin('color:transparent', COLOR_TRANSPARENT)
presets.add_builtin('color:background_gray', Color(215, 215, 215))
presets.add_builtin('color:white', Color(1, 1, 1))
presets.add_builtin('color:gray', Color(215, 215, 215))
presets.add_builtin('color:lightblue', Color(.7, .8, .9))

class ResidueColormap(object):
    """A group:color colormap."""
    def __init__(self, *args, **kw):
        self.mappings = dict(*args, **kw)
        self.settings = None
        
    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            return False
        return (other is self) or other.mappings == self.mappings
    
    def __hash__(self):
        return reduce(lambda l, r: (l << 1) ^ r, (hash(t) for t in self.mappings.items()))

    def flatten(self):
        return dict((aa, color) for residues, color in self.mappings.items() for aa in residues)
    
    def items(self):
        return self.mappings.items()

    def to_str(self):
        return '/'.join("%s:%s" % t for t in self.mappings.items())

    @classmethod
    def from_str(cls, string):
        return cls.from_mappings((r, Color.from_str(c)) for r, c in (s.split(':') for s in string.split('/')))
    
    @classmethod
    def from_mappings(cls, mappings):
        colormap = cls()
        colormap.mappings.update(mappings)
        return colormap
    
    @classmethod
    def from_settings(cls, setting):
        colormap = setting.get_value()
        colormap.settings = setting
        return colormap
    
    def update(self, *args, **kw):
        self.mappings.update(*args, **kw)

def find(sequence, test, default=None):
    try:
        return (x for x in sequence if test(x)).next()
    except StopIteration:
        return default

class RegexColormap(object):
    """A composite colormap where regexes define groups."""
    def __init__(self):
        self.mappings = []
        self.settings = None

    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            return False
        return (other is self) or other.mappings == self.mappings
    
    def __hash__(self):
        return reduce(lambda l, r: (l << 1) ^ r, (hash(t) for t in self.mappings), 0)

    @classmethod
    def from_mappings(cls, mappings):
        colormap = cls()
        colormap.update(mappings)
        return colormap

    @classmethod
    def from_settings(cls, setting):
        colormap = setting.get_value()
        colormap.settings = setting
        return colormap

    def items(self):
        return self.mappings
    
    def update(self, mappings):
        for regex, color in mappings:
            if isinstance(regex, basestring):
                regex = re.compile(regex)
            mapping = find(self.mappings, lambda x: x[0]==regex)
            if mapping:
                i = self.mappings.index(mapping)
                self.mappings[i] = (mapping[0], color)
            else:
                self.mappings.append((regex, color))

    def to_str(self):
        return '/'.join("%s:%s" % (r.pattern, c) for r, c in self.mappings.items())

    @classmethod
    def from_str(cls, string):
        return cls.from_mappings((r, Color.from_str(c)) for r, c in (s.split(':') for s in string.split('/')))
    

class ColorMappingSetting(ColorSetting):
    key_attrib = 'residues'
    def __init__(self, mapping=None, frompreset=None, preset_registry=None):
        key = color = None
        if mapping is not None:
            key, color = mapping 
        ColorSetting.__init__(self, color, frompreset, preset_registry)
        self.key = key
        
    @classmethod
    def from_value(cls, map, preset_registry=None):
        key, color = map
        return cls((key, color.to_str()), color.frompreset, preset_registry)
        
    def parse(self, element):
        ColorSetting.parse(self, element)
        self.key = element.attrib[self.key_attrib]
        
    def encode(self, element):
        ColorSetting.encode(self, element)
        element.attrib[self.key_attrib] = self.key
        
    def get_value(self):
        color = ColorSetting.get_value(self)
        return (self.key, color)

class ColormapSetting(SettingList):
    tag = 'map'
    element_setting_type = ColorMappingSetting
    colormap_class = ResidueColormap.from_mappings
    @classmethod
    def from_value(cls, colormap, preset_registry=None):
        if colormap.settings:
            return colormap.settings
        settings = [cls.element_setting_type.from_value(v, preset_registry) for v in colormap.items()]
        return cls(settings)
        
    def get_value(self):
        mappings = []
        if self.frompreset:
            mappings = Setting.get_value(self).items()
        mappings.extend(self.get_specified())
        colormap = self.colormap_class(mappings)
        if self.name:
            colormap.frompreset = self.name
        return colormap

class RegexColorMappingSetting(ColorMappingSetting):
    key_attrib = 'regex'
    def parse(self, element):
        ColorMappingSetting.parse(self, element)
        self.key = re.compile(self.key)
        
    def encode(self, element):
        ColorSetting.encode(self, element)
        element.attrib[self.key_attrib] = self.key.pattern

class RegexColormapSetting(ColormapSetting):
    element_setting_type = RegexColorMappingSetting
    colormap_class = RegexColormap.from_mappings

presets.register_type('colormap', ColormapSetting)
presets.register_type('colormap.regex', RegexColormapSetting)
presets.add_builtin('color:clustalx_blue', Color(25, 127, 229)) 
presets.add_builtin('color:clustalx_cyan', Color(25, 178, 178))
presets.add_builtin('color:clustalx_green', Color(25, 204, 25))
presets.add_builtin('color:clustalx_magenta', Color(204, 76, 204))
presets.add_builtin('color:clustalx_orange', Color(229, 153, 76))
presets.add_builtin('color:clustalx_pink', Color(229, 127, 127))
presets.add_builtin('color:clustalx_red', Color(229, 51, 25))
presets.add_builtin('color:clustalx_yellow', Color(204, 204, 0))
cm = ResidueColormap(VILMAFCW=presets.get_value('color:clustalx_blue'), 
                     HY=presets.get_value('color:clustalx_cyan'),
                     TSNQ=presets.get_value('color:clustalx_green'),
                     DE=presets.get_value('color:clustalx_magenta'),
                     G=presets.get_value('color:clustalx_orange'),
                     KR=presets.get_value('color:clustalx_red'),
                     P=presets.get_value('color:clustalx_yellow'))
presets.add_builtin('colormap:clustalx', cm)

presets.add_builtin('colormap.regex:highlight_unaligned', 
    RegexColormap.from_mappings([
        (r'[.-]+', Color(1.0, 1.0, 1.0)),
        (r'(?<!-)-+(?!-)', Color(25, 127, 229)),
        (r'^[.-]+|[.-]+$', Color(229, 51, 25)),
        (r'[a-z]+', Color.from_str('#1919dddd1919')), #Color(25, 204, 25)),
        (r'[xX]+', Color(.7, 0, .9))]))

def blend(amount, color1, color2):
    args = [v + (v2 - v) * amount for v, v2 in zip(color1.rgba, color2.rgba)]
    return Color(*args)

class Gradient(object):
    def __init__(self):
        self.colorstops = []
        self.settings = None
        
    def __hash__(self):
        return hash(tuple(self.colorstops))

    def __eq__(self, other):
        return isinstance(other, Gradient) and other.colorstops == self.colorstops
    
    @classmethod
    def from_colorstops(cls, *stops):
        g = cls()
        g.add_colorstops(*stops)
        return g

    @classmethod
    def from_settings(cls, setting):
        gradient = setting.get_value()
        gradient.settings = setting
        return gradient
    
    @classmethod
    def from_str(cls, string):
        return cls.from_colorstops((float(p), Color.from_str(c)) for s in string.split('/') for p, c in s.split(':', 1))

    def to_str(self):
        return "/".join("%r:%s" % (p, c.to_str()) for p, c in self.colorstops)
    
    def add_colorstop(self, offset, color):
        self.add_colorstops((offset, color))
        
    def add_colorstops(self, *stops):
        self.colorstops.extend(((float(o), c) for o, c in stops))
        self.colorstops.sort(key=lambda cs: cs[0])
        
    def get_color_from_offset(self, offset):
        if not self.colorstops:
            return Color(0, 0, 0, 0)
        if offset < self.colorstops[0][0]:
            return self.colorstops[0][1]
        i = 0
        last = len(self.colorstops) - 1
        while i < last:
            o, c = self.colorstops[i]
            o2, c2 = self.colorstops[i + 1]
            if o <= offset < o2:
                ratio = (offset - o) / (o2 - o)
                return blend(ratio, c, c2)
            i += 1
        return self.colorstops[-1][1]
    
    def get_array_from_offset(self, offset):
        if not self.colorstops:
            return COLOR_TRANSPARENT_ARRAY
        if offset >= self.colorstops[-1][0]:
            return self.colorstops[-1][1].array
        if offset < self.colorstops[0][0]:
            return self.colorstops[0][1].array
        i = len(self.colorstops) - 2
        for i in range(len(self.colorstops) - 2, -1, -1):
            offset1, color1 = self.colorstops[i]
            if offset < offset1:
                continue
            if offset == offset1:
                return color1
            offset2, color2 = self.colorstops[i + 1]
            ratio = (offset - offset1) / (offset2 - offset1)
            return numpy.array(ratio * color2.array + (1 - ratio) * color1.array, dtype=numpy.uint8)
    
    def to_linear_gradient(self, x0, y0, x1, y1):
        g = cairo.LinearGradient(x0, y0, x1, y1)
        for offset, color in self.colorstops:
            g.add_color_stop_rgba(offset, *color.rgba)
        return g

class ColorstopSetting(ColorMappingSetting):
    key_attrib = 'position'
    def parse(self, element):
        ColorMappingSetting.parse(self, element)
        self.key = float(self.key)

    def encode(self, element):
        ColorSetting.encode(self, element)
        element.attrib[self.key_attrib] = repr(self.key)

class GradientSetting(SettingList):
    tag = 'colorstop'
    element_setting_type = ColorstopSetting
    @classmethod
    def from_value(cls, gradient, preset_registry=None):
        if gradient.settings:
            return gradient.settings
        settings = [cls.element_setting_type.from_value(v) for v in gradient.colorstops]
        return cls(settings)

    def get_value(self):
        if self.frompreset:
            gradient = Setting.get_value(self)
        else:
            gradient = Gradient()
        gradient.add_colorstops(*self.get_specified())
        if self.name:
            gradient.frompreset = self.name
        return gradient

presets.register_type('gradient', GradientSetting)
gradient_jet = Gradient.from_colorstops((0.0, Color.from_str('blue')), 
                                        (.33, Color.from_str('cyan')),
                                        (.66, Color.from_str('yellow')),
                                        (.85, Color.from_str('red')),
                                        (1.0, Color.from_str('red4')))
presets.add_builtin('gradient:jet', gradient_jet)
presets.add_builtin('gradient:ryg', Gradient.from_colorstops((0.0, Color(1,0,0)), (.50, Color(1,1,0)), (1.0, Color(0,1,0))))
