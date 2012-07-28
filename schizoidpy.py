# encoding: UTF-8

from math import sqrt
from re import match
from datetime import datetime
from psychopy.monitors import Monitor
from psychopy.gui import Dlg
from psychopy.core import wait
from psychopy.logging import debug, warning
from psychopy.event import Mouse, getKeys, clearEvents
from psychopy.visual import \
    Window, Rect, Circle, TextStim, RatingScale
import pyglet
import wx
import numpy
import json
from socket import gethostname

# ------------------------------------------------------------
# Private helper functions and classes
# ------------------------------------------------------------

def staggered(l):
    'staggered([1, 2, 3]) → [(1, 2), (2, 3), (3, None)]'
    return zip(l, list(l[1:]) + [None])

def tuplecat(a, b): return (
  b if a is () else
  a if b is () else
 (a if isinstance(a, tuple) else (a,)) +
 (b if isinstance(b, tuple) else (b,)))

class dkey_prefix(object):
    def __init__(self, task, my_prefix):
        self.task = task
        self.my_prefix = my_prefix if isinstance(my_prefix, tuple) else (my_prefix,)
    def __enter__(self):
        self.task.cur_dkey_prefix = tuplecat(self.my_prefix, self.task.cur_dkey_prefix)
    def __exit__(self, _1, _2, _3): 
        self.task.cur_dkey_prefix = self.task.cur_dkey_prefix[len(self.my_prefix):]

class timestamps(object):
   def __init__(self, task, dkey):
       self.task = task
       self.dkey = dkey
   def timestamp(self, i):
       with self.task.dkey_prefix('times'):
           self.task.save(tuplecat(self.dkey, i),
               datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.%f"))
   def __enter__(self):
       self.timestamp(0)
   def __exit__(self, _1, _2, _3):
       self.timestamp(1)

class showing(object):
    def __init__(self, task, *stimuli):
        self.task = task
        self.stimuli = stimuli
    def __enter__(self):
        for s in self.stimuli: self.task.implicitly_draw.append(s)
    def __exit__(self, _1, _2, _3):
        for s in self.stimuli: self.task.implicitly_draw.remove(s)

class hiding(object):
    def __init__(self, task, *stimuli):
        self.task = task
        self.stimuli = stimuli
    def __enter__(self):
        self.old_implicitly_draw = self.task.implicitly_draw[:]
        for s in self.stimuli: self.task.implicitly_draw.remove(s)
    def __exit__(self, _1, _2, _3):
        self.task.implicitly_draw = self.old_implicitly_draw

class Button(object):
    def __init__(self, task, x, y, string):
        self.task, self.x, self.y, self.string = task, x, y, string
        self.circle = Circle(task.win,
            task.button_radius, pos = (x, y),
            lineColor = 'black', lineWidth = 3, edges = 64,
            fillColor = 'lightgray')
        self.text = task.text(x, y, string)
        self.was_pressed = False

    def draw(self):
        self.circle.draw()
        self.text.draw()

    def inside(self, (x, y)): return (
        sqrt((self.x - x)*(self.x - x) + (self.y - y)*(self.y - y))
        <= self.task.button_radius)

    def activated(self):
        if self.was_pressed or (
                any(self.task.mouse.getPressed()) and
                self.inside(self.task.mouse.getPos())):
            self.was_pressed = True
            return True
        return False

class StimGroup(object):
    def __init__(self, *stimuli):
        self.stimuli = stimuli
    def draw(self):
        for x in self.stimuli: x.draw()

class SchizoidDlg(Dlg):
    """A Dlg without a Cancel button and with the ability to
    set field widths."""
    # Initially copied from psychopy.gui (which is copyright
    # 2011 Jonathan Peirce and available under GPL v3).

    def show(self):
        buttons = wx.BoxSizer(wx.HORIZONTAL)
        OK = wx.Button(self, wx.ID_OK, " OK ")
        OK.SetDefault()
        buttons.Add(OK)
        self.sizer.Add(buttons,1,flag=wx.ALIGN_RIGHT|wx.ALIGN_BOTTOM,border=5)

        self.SetSizerAndFit(self.sizer)
        self.ShowModal()

        self.data=[]
        #get data from input fields
        for n in range(len(self.inputFields)):
            thisName = self.inputFieldNames[n]
            thisVal = self.inputFields[n].GetValue()
            thisType= self.inputFieldTypes[n]
            #try to handle different types of input from strings
            debug("%s: %s" %(self.inputFieldNames[n], unicode(thisVal)))
            if thisType in [tuple,list,float,int]:
                #probably a tuple or list
                exec("self.data.append("+thisVal+")")#evaluate it
            elif thisType==numpy.ndarray:
                exec("self.data.append(numpy.array("+thisVal+"))")
            elif thisType in [str,unicode,bool]:
                self.data.append(thisVal)
            else:
                warning('unknown type:'+self.inputFieldNames[n])
                self.data.append(thisVal)
        self.OK=True
        self.Destroy()

    def addField(self, label='', initial='', color='', tip='', width=None):
        """
        Adds a (labelled) input field to the dialogue box, optional text color
        and tooltip. Returns a handle to the field (but not to the label).
        """
        self.inputFieldNames.append(label)
        self.inputFieldTypes.append(type(initial))
        if type(initial)==numpy.ndarray:
            initial=initial.tolist() #convert numpy arrays to lists
        container=wx.GridSizer(cols=2, hgap=10)
        #create label
        labelLength = wx.Size(9*len(label)+16,25)#was 8*until v0.91.4
        inputLabel = wx.StaticText(self,-1,label,
                                        size=labelLength,
                                        style=wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_RIGHT)
        if len(color): inputLabel.SetForegroundColour(color)
        container.Add(inputLabel, 1, wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_RIGHT)
        #create input control
        if type(initial)==bool:
            inputBox = wx.CheckBox(self, -1)
            inputBox.SetValue(initial)
        else:
            inputLength = wx.Size(
                width if width is not None else 
                    max(50, 5*len(unicode(initial))+16),
                25)
            inputBox = wx.TextCtrl(self,-1,unicode(initial),size=inputLength)
        if len(color): inputBox.SetForegroundColour(color)
        if len(tip): inputBox.SetToolTip(wx.ToolTip(tip))

        container.Add(inputBox,1, wx.ALIGN_CENTER_VERTICAL)
        self.sizer.Add(container, 1, wx.ALIGN_CENTER)

        self.inputFields.append(inputBox)#store this to get data back on OK
        return inputBox

# ------------------------------------------------------------
# The Task class
# ------------------------------------------------------------

class Task(object):

    #####################
    # Public
    #####################

    def __init__(self,
            button_radius = .1, # In norm units
            fixation_cross_length = 50, # Pixels
            fixation_cross_thickness = 5, # Pixels
            pause_time = .1, # Seconds
            approx_dialog_box_width = 200, # Pixels
            html_font_name = 'sans-serif',
            html_font_size = 20): # Points

        vs = locals()
        del vs['self']
        for k, v in vs.items(): setattr(self, k, v)

        self.data = {}
        self.cur_dkey_prefix = ()
        self.implicitly_draw = []

        pyglet_screen = pyglet.window.get_platform().get_default_display().get_default_screen()
        self.screen_width, self.screen_height = pyglet_screen.width, pyglet_screen.height
        self.win = Window((self.screen_width, self.screen_height),
            monitor = 'testMonitor',
            winType = 'pyglet', fullscr = False,
            units = 'norm', color = 'white')
        self.mouse = Mouse(win = self.win)
        self.fixation_cross = StimGroup(
            Rect(self.win, fillColor = 'black', lineColor = 'black',
                units = 'pix',
                width = self.fixation_cross_length, height = self.fixation_cross_thickness),
            Rect(self.win, fillColor = 'black', lineColor = 'black',
                units = 'pix',
                width = self.fixation_cross_thickness, height = self.fixation_cross_length))

        self.save(('sys', 'hostname'), gethostname())
        self.save(('sys', 'resolution'), (self.screen_width, self.screen_height));

    def save(self, key, value):
        """Set a value in data with Perl-style autovivification, so
        o.save(('times', 3, 'orange'), 'x') is like
        o.data['times'][3]['orange'] = 'x' but works even if the
        intermediate data structures don't exist yet (or, in the
        case of lists, are too short)."""
        key = tuplecat(tuple(self.cur_dkey_prefix), key)
        if isinstance(key, tuple):
            seq = self.data
            for k, next_k in staggered(key):
                newobj = (
                     value if next_k is None else
                     [] if isinstance(next_k, int) else
                     {}) # if isinstance(next_k, str)
                if isinstance(seq, dict):
                    if k not in seq:
                        seq[k] = newobj
                elif isinstance(seq, list):
                    if len(seq) - 1 < k:
                        # The list is too short. Pad it out with Nones.
                        seq[len(seq):] = (k + 1 - len(seq)) * [None]
                    if seq[k] is None:
                        seq[k] = newobj
                else: raise KeyError
                seq = seq[k]
        elif isinstance(key, str):
            self.data[key] = value
        else: raise KeyError

    # The below are silly, I know, but
    #     with task.dkey_prefix("phooey"):
    # looks better than
    #     with dkey_prefix(task, "phooey"):
    def dkey_prefix(self, new_prefix):
        '''"with task.dkey_prefix('questionnaire'): …" prefixes
        'questionnaire' to the dkeys of all task.save() calls,
        explicit or implicit.'''
        return dkey_prefix(self, new_prefix)
    def timestamps(self, dkey):
        '''"with task.timestamps('foo'): …" makes two timestamps
        for the dkey 'foo', one when entering the block and one
        when exiting it.'''
        return timestamps(self, dkey)
    def showing(self, *stimuli):
        '''"with task.showing(foo, bar): …" ensures that foo and
        bar are implicitly drawn on each call to task.draw().'''
        return showing(self, *stimuli)
    def hiding(self, *stimuli):
        "Hides stimuli that would be displayed by 'showing'."
        return hiding(self, *stimuli)

    def get_subject_id(self, window_title):
        dialog = Dlg(title = window_title)
        dialog.addText('')
        dialog.addField('Subject ID:', 'test')
        dialog.addText('')
        dialog.show()
        if not dialog.OK: exit()
        self.save('subject', dialog.data[0])

    def pause(self):
        wait(self.pause_time)

    def text(self, x, y, string, hAlign = 'center', vAlign = 'center', wrap = None, color = 'black'):
        return TextStim(self.win,
            text = string, pos = (x, y), color = color,
            height = .075, alignHoriz = hAlign, alignVert = vAlign,
            wrapWidth = wrap)

    def html(self, x, y, string, hAlign = 'center', vAlign = 'center', wrap = None, color = 'black'):
        # Note that when hAlign = 'center', the stimuli generated
        # with this method, unlike task.text(), are centered with
        # respect to the entire wrap width, not their actual content
        # width. I failed to fix this.
        text = self.text(x, y, string, hAlign, vAlign, wrap, color)
        if hAlign == 'right':
           raise Exception('Not implemented: hAlign = "right"')
        pyg = pyglet.text.HTMLLabel(
            #x = self.screen_width/2,
            text = text.text,# if hAlign == 'left' else
                   #'<center>{}</center>'.format(text.text),
            #anchor_x = text.alignHoriz,
            anchor_y = text.alignVert,
            multiline = True, width = text._wrapWidthPix)
        #if hAlign == 'center':
        #    print pyg.content_width, "vs.", pyg.width
        #    pyg.x = (text._wrapWidthPix - pyg.content_width)/2
        pyg.font_name = self.html_font_name
        pyg.font_size = self.html_font_size
        text._pygletTextObj = pyg
        return text
        
    def button(self, x, y, string):
        return Button(self, x, y, string)

    def rating_scale(self, stretchHoriz = 1.75, **a): return RatingScale(self.win,
        textColor = 'black', lineColor = 'black',
        markerStyle = 'circle', markerColor = 'darkgreen',
        stretchHoriz = stretchHoriz,
        showValue = False, allowSkip = False, showScale = False,
        escapeKeys = ['escape'], singleClick = True, showAccept = False,
        **a)

    def likert_scale(self, x = 0, y = -.7,
            scale_points = 7,
            anchors = ('min', 'max')):
        return self.rating_scale(
            pos = (x, y),
            low = 1, lowAnchorText = anchors[0],
            high = scale_points, highAnchorText = anchors[1])

    def wait_screen(self, time_to_wait, *stimuli):
        'Display some stimuli for a given amount of time.'
        self.draw(*stimuli)
        wait(time_to_wait)

    def okay_screen(self, dkey, *stimuli):
        self.button_screen(dkey,
            *(stimuli + (self.button(0, -.5, 'Next'),)))

    def instructions(self, dkey, string, html = False):
        self.okay_screen(dkey,
            self.html(0, .8, string, vAlign = 'top')
              if html
              else self.text(0, .8, string, vAlign = 'top'))

    def button_screen(self, dkey, *stimuli):
        """Display some stimuli (including at least one button)
        until the subject presses a button."""
        buttons = [x for x in stimuli if isinstance(x, Button)]
        with self.timestamps(dkey):
            while all([not x.activated() for x in buttons]):
                if getKeys(['escape']): exit()
                clearEvents()
                self.draw(*stimuli)
        if len(buttons) > 1:
          # No sense in saving the value of the button if there's
          # only one.
            self.save(dkey, [x for x in buttons if x.activated()][0].string)
        self.pause()

    def scale_screen(self, dkey, *stimuli):
        """Display some stimuli (including at least one scale) until
        the subject has responded to all the scales."""
        scales = filter(lambda x: isinstance(x, RatingScale), stimuli)
        clearEvents()
        with self.timestamps(dkey):
            while any([x.noResponse for x in scales]):
                self.draw(*stimuli)
        self.pause()
        rs = [x.getRating() for x in scales]
        self.save(dkey, rs[0] if len(rs) == 1 else rs)

    def discrete_rating_screen(self, dkey, string, **opts):
        self.scale_screen(dkey,
            self.text(0, .3, string),
            self.likert_scale(**opts))

    def string_entry_screen(self, dkey, prompt,
            dialog_field_label, dialog_hint, dialog_error,
            extractor,
            trim = True, accept_blank = False,
            width = None):
        """Ask for a string with the given prompt. The extractor should
        be a function that translates the user's input into
        whatever should go into 'data' or returns None if the input
        is invalid. dialog_field_label, dialog_hint, and dialog_error
        are strings used in the dialog box."""
        self.draw(
            self.text(0, .8, prompt, vAlign = 'top'))
        with self.timestamps(dkey):
            trying_again = False
            while True:
                dialog = SchizoidDlg(
                    title = 'Entry',
                    pos = (self.screen_width/2 - self.approx_dialog_box_width, .85 * self.screen_height))
                dialog.addText(' ' * 45)
                dialog.addField(dialog_field_label, width = width)
                dialog.addText(dialog_error if trying_again else dialog_hint)
                dialog.show()
                trying_again = True
                  # Not so quite yet, but 'twill be so if we rerun
                  # the loop.
                inp = dialog.data[0]
                if trim:
                    inp = inp.strip()
                if not accept_blank and (inp.isspace() or inp == ''):
                    continue
                inp = extractor(inp)
                if inp is not None:
                    break
        self.pause()

    def text_entry_screen(self, dkey, string, accept_blank = False):
        "Ask for arbitrary text with the given prompt."
        self.string_entry_screen(dkey, string, width = 200,
            dialog_field_label = 'Text:',
            dialog_hint = 'Type some text.',
            dialog_error = 'Type some text.',
            accept_blank = False,
            extractor = lambda s: s)

    def nonneg_int_entry_screen(self, dkey, string):
        "Ask for a nonnegative integer with the given prompt."
        self.string_entry_screen(dkey, string,
            dialog_field_label = 'Number:',
            dialog_hint = 'Enter a number.',
            dialog_error = 'Invalid number; please try again.',
            extractor = lambda s: s if s.isdigit() else None)

    def write_data(self, path):
        with open(path, "w") as out:
            json.dump(self.data, out, sort_keys = True, indent = 2)

    #####################
    # Private
    #####################

    def draw(self, *stimuli):
       for s in self.implicitly_draw: s.draw()
       for s in stimuli: s.draw()
       self.win.flip()
