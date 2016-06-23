# encoding: UTF-8

from copy import deepcopy
from datetime import datetime
from socket import gethostname
from time import sleep
import os.path
import json
import numpy
import wx
import pyglet
from psychopy.monitors import Monitor
import psychopy.gui; from psychopy.gui import Dlg
from psychopy.core import Clock, wait
from psychopy.logging import debug, warning
from psychopy.event import Mouse, getKeys, clearEvents
from psychopy.visual import \
    Window, Rect, Circle, TextStim, RatingScale

standard_actiview_trigger_codes = dict(
    START_LISTENING = 255,
    STOP_LISTENING = 256,
    RESET_PINS = 0)

# ------------------------------------------------------------
# Public helper functions and classes
# ------------------------------------------------------------

class StimGroup(object):
    def __init__(self, stimuli):
        self.stimuli = stimuli
    def draw(self):
        for x in self.stimuli: x.draw()

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

def abs_timestamp_str():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.%f")

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
   def __enter__(self):
       self.task.save_timestamp(self.dkey, 0)
   def __exit__(self, _1, _2, _3):
       self.task.save_timestamp(self.dkey, 1)

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
    def __init__(self, task, x, y, string, trigger_code = None):
        self.task, self.x, self.y, self.string, self.trigger_code = task, x, y, string, trigger_code
        self.circle = Circle(task.win,
            task.button_radius, pos = (x, y),
            lineColor = 'black', lineWidth = 3, edges = 64,
            fillColor = 'lightgray')
        self.text = task.text(x, y, string)
        self.was_pressed = False

    def draw(self):
        self.circle.draw()
        self.text.draw()

    def activated(self):
        if self.was_pressed:
            return True
        if (any(self.task.mouse.getPressed()) and
            self.circle.contains(self.task.mouse)):
            self.was_pressed = True
            if self.trigger_code is not None:
                self.task.trigger(self.trigger_code)
            return True
        return False

def init_wx():
    if not hasattr(psychopy.gui, 'app'):
        psychopy.gui.app = wx.PySimpleApp()
          # This is what PsychoPy does if you make a Dlg before
          # a wx.App exists.

wx_text_wrap_width = 300
def wrapped_text(parent, string):
    x = wx.StaticText(parent, -1, string)
    x.Wrap(wx_text_wrap_width)
    return x

def box(sizer_of, orientation, *contents):
    box = wx.BoxSizer(orientation)
    for c in contents:
        if   isinstance(c, list):  box.AddMany(c)
        elif isinstance(c, tuple): box.Add(*c)
        else:                      box.Add(c)
    if sizer_of is not None: sizer_of.SetSizer(box)
    return box

def okay(parent, default = False):
    b = wx.Button(parent, wx.ID_OK)
    if default: b.SetDefault()
    return b

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
        #create label
        labelLength = wx.Size(9*len(label)+16,25)#was 8*until v0.91.4
        inputLabel = wx.StaticText(self,-1,label,
                                        size=labelLength,
                                        style=wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_RIGHT)
        if len(color): inputLabel.SetForegroundColour(color)
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

        self.sizer.Add(
            box(None, wx.HORIZONTAL,
                (inputLabel, 0, wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_RIGHT),
                (inputBox, 0, wx.ALIGN_CENTER_VERTICAL)),
            1, wx.ALIGN_CENTER)

        self.inputFields.append(inputBox)#store this to get data back on OK
        return inputBox

class QuestionnaireDialog(wx.Dialog):
    def __init__(self, parent, title, scale_levels,
          questions, questions_per_page,
          font_size = None, column_filler_width = 100):
        wx.Dialog.__init__(self, parent, -1, title, wx.DefaultPosition)

        if font_size:
            font = self.GetFont()
            font.SetPointSize(font_size)
            self.SetFont(font)

        notebook = wx.Notebook(self, style = wx.BK_DEFAULT)
        self.questions = (
            deepcopy(questions)
            if isinstance(questions[0], dict)
            else [{'id': k, 'text': v} for k, v in enumerate(questions)])

        for qn1 in range(0, len(questions), questions_per_page):
            panel = wx.Panel(notebook)

            fgs = wx.FlexGridSizer(cols = 1 + len(scale_levels),
                vgap = 5, hgap = 5)
            # Add horizontal spaces to make all the response
            # columns the same width.
            fgs.Add(wx.Size(0, 0))
            fgs.AddMany(len(scale_levels) * [wx.Size(column_filler_width, 0)])
            # Add the column headers.
            fgs.Add(wx.Size(0, 0))
            for s in scale_levels:
                fgs.Add(wrapped_text(panel, s), 0, wx.ALIGN_CENTER)
            # Add the questions and radio buttons.
            for q in self.questions[qn1 : qn1 + questions_per_page]:
                wx.RadioButton(panel, pos = (-50, -50), style = wx.RB_GROUP)
                  # Create a hidden radio button so that it appears that no
                  # button is selected by default.
                q['buttons'] = map(lambda _: wx.RadioButton(panel, -1), scale_levels)
                fgs.Add(wrapped_text(panel, q['text']), 0, wx.ALIGN_CENTER_VERTICAL)
                for b in q['buttons']:
                    fgs.Add(b, 0, wx.ALIGN_CENTER)
            # Add some trailing vertical space.
            fgs.Add(wx.Size(0, 5))
            panel.SetSizer(fgs)

            notebook.AddPage(panel, "Page %d" % (qn1 / questions_per_page + 1,))

        b = box(self, wx.VERTICAL,
            notebook,
            (okay(self), 0, wx.ALIGN_CENTER_HORIZONTAL)).Fit(self)

class PoisonPill: pass

def trigger_worker(queue, trigger_code_delay, inpout32_addr):
    if inpout32_addr is not None:
        from ctypes import windll
        send = lambda x: windll.inpout32.Out32(inpout32_addr, x)
    else:
        from psychopy.parallel import setData
        send = setData
    while True:
        trigger_code = queue.get(True, int(1e6))
          # The long timeout (11 days) is to work around a Python
          # bug.
          # http://stackoverflow.com/a/1408476
        if trigger_code == PoisonPill:
            return
        send(trigger_code)
        sleep(trigger_code_delay)
        send(standard_actiview_trigger_codes['RESET_PINS'])
        sleep(trigger_code_delay)

# ------------------------------------------------------------
# The Task class
# ------------------------------------------------------------

class Task(object):

    #####################
    # Public
    #####################

    def __init__(self,
            absolute_timestamps = False,
            send_actiview_trigger_codes = False,
              # If this is on, you can use the 'trigger' method
              # to non-blockingly send EEG trigger signals
              # through the parallel port to a machine running
              # BioSemi ActiView. Otherwise, 'trigger' silently
              # does nothing. Beware that this feature uses
              # the multiprocessing module, so on Windows,
              # your program will need to be headed with
              #     if __name__ == '__main__':
              # or you'll forkbomb yourself.
            inpout32_addr = None,
            trigger_code_delay = .05, # Seconds
            pause_time = .1, # Seconds
            debug_log_dir = None,
              # Set it to a string to write a debug log. The
              # debug log will have similar information as the
              # final JSON output, but it's written line-by-line
              # so you can read it if the task program crashes.
            double_draw = False,
              # Draw everything twice to work around
              # a graphics bug.
            shrink_screen = False,
              # Draw a slightly smaller screen to avoid a bug
              # on Windows 7 involving some kind of automatic
              # fullscreening.
            bg_color = 'white',
            button_radius = .1, # Norm units
            okay_button_pos = (0, -.5), # Norm units
            fixation_cross_length = 50, # Pixels
            fixation_cross_thickness = 5, # Pixels
            fixation_cross_color = 'black',
            string_entry_box_y = -.4, # Norm units
            approx_dialog_box_width = 200, # Pixels
              # This option should be set to an estimate of how
              # the dialog boxes appear on your system, not what
              # you want. It's used to position the boxes.
            font_name = 'Verdana',
            html_font_size = 20): # Points

        vs = locals()
        del vs['self']
        for k, v in vs.items(): setattr(self, k, v)

        self.debug_log = None
        if self.debug_log_dir:
            self.debug_log = open(
                os.path.join(self.debug_log_dir, 'debuglog-{}.txt'.format(
                    datetime.utcnow().strftime('%Y-%m-%d-%H-%M-%S-%f'))),
                'w',
                buffering = 0)

        self.data = {}
        self.cur_dkey_prefix = ()
        self.implicitly_draw = []

        if self.send_actiview_trigger_codes:
            import multiprocessing
            self.trigger_queue = multiprocessing.Queue()
            self.trigger_worker = multiprocessing.Process(
                target = trigger_worker, args = (self.trigger_queue, self.trigger_code_delay, inpout32_addr))
            self.trigger_worker.start()
            self.save(('sys', 'trigger_worker_pid'), self.trigger_worker.pid)
            self.trigger(standard_actiview_trigger_codes['START_LISTENING'])

        pyglet_screen = pyglet.window.get_platform().get_default_display().get_default_screen()
        self.screen_width, self.screen_height = pyglet_screen.width, pyglet_screen.height
        if self.shrink_screen:
            self.screen_width -= 5
            self.screen_height -= 5
        self.win = Window((self.screen_width, self.screen_height),
            monitor = 'testMonitor',
            winType = 'pyglet', fullscr = False,
            units = 'norm', color = bg_color)
        self.mouse = Mouse(win = self.win)
        self.fixation_cross = StimGroup((
            Rect(self.win, fillColor = fixation_cross_color, lineColor = fixation_cross_color,
                units = 'pix',
                width = self.fixation_cross_length, height = self.fixation_cross_thickness),
            Rect(self.win, fillColor = fixation_cross_color, lineColor = fixation_cross_color,
                units = 'pix',
                width = self.fixation_cross_thickness, height = self.fixation_cross_length)))

        self.save(('sys', 'hostname'), gethostname())
        self.save(('sys', 'resolution'), (self.screen_width, self.screen_height))
        self.save(('sys', 'pid'), os.getpid())

        self.save(('overall_timing', 'started'), abs_timestamp_str())

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
        else:
            raise KeyError
        if self.debug_log is not None:
            print >>self.debug_log, 'Saved', repr(key), '|||', repr(value)

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

    def start_clock(self):
        self.clock = Clock()

    def set_pyglet_visible(self, visible = True):
        self.win.winHandle.set_visible(visible)

    def trigger(self, code):
        if self.send_actiview_trigger_codes:
            self.trigger_queue.put(code)

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
            height = .075, font = self.font_name,
            alignHoriz = hAlign, alignVert = vAlign,
            wrapWidth = wrap)

    def html(self, x, y, string, hAlign = 'center', vAlign = 'center', wrap = None, color = 'black', font_size = None):
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
        pyg.font_name = self.font_name
        pyg.font_size = font_size if font_size is not None else self.html_font_size
        text._pygletTextObj = pyg
        return text
        
    def button(self, x, y, string, trigger_code = None):
        return Button(self, x, y, string, trigger_code)

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

    def wait_screen_till(self, timer, *stimuli):
        'Display some stimuli until the CountdownTimer reaches 0.'
        if timer.getTime() > 0:
            self.draw(*stimuli)
            wait(timer.getTime())

    def okay_screen(self, dkey, *stimuli):
        self.button_screen(dkey, *(stimuli + (self.button(
            self.okay_button_pos[0],
            self.okay_button_pos[1],
            'Next'),)))

    def instructions(self, dkey, string, html = False, wrap = None):
        self.okay_screen(dkey,
            self.html(0, .8, string, vAlign = 'top', wrap = wrap)
              if html
              else self.text(0, .8, string, vAlign = 'top', wrap = wrap))

    def button_screen(self, dkey, *stimuli):
        """Display some stimuli (including at least one button)
        until the subject presses a button. Return the pressed
        button's string."""
        buttons = [x for x in stimuli if isinstance(x, Button)]
        with self.timestamps(dkey):
            while all([not x.activated() for x in buttons]):
                if getKeys(['escape']): exit()
                clearEvents()
                self.draw(*stimuli)
        val = [x for x in buttons if x.activated()][0].string
        if len(buttons) > 1:
          # No sense in saving the value of the button if there's
          # only one.
            self.save(dkey, val)
        self.pause()
        return val

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

    def keypress_screen(self, dkey, keys = None, *stimuli):
        """Display some stimuli until the subject presses one of
        the keys. 'keys' can be None, a string, a dictionary, or
        some other iterable. If it's a dictionary, the
        corresponding value is saved (and returned). The Escape
        key is reserved."""
        checkfor = (
            None if keys is None else
            ['escape', keys] if isinstance(keys, str) or isinstance(keys, unicode) else
            ['escape'] + keys.keys() if isinstance(keys, dict) else
            ['escape'] + list(keys))
        clearEvents()
        v = None
        with self.timestamps(dkey):
            while True:
                pressed = getKeys(checkfor)
                clearEvents()
                if 'escape' in pressed:
                    exit()
                if len(pressed) == 1:
                    if isinstance(keys, dict):
                        v = keys[pressed[0]]
                        self.save(dkey, v)
                    break
                self.draw(*stimuli)
        self.pause()
        return v

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
                    pos = (
                        self.screen_width/2 - self.approx_dialog_box_width,
                        self.screen_height/2 - self.string_entry_box_y * self.screen_height/2))
                dialog.addText(' ' * 45)
                dialog.addField(dialog_field_label, width = width)
                dialog.addText(dialog_error if trying_again else dialog_hint)
                dialog.inputFields[0].SetFocus()
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
                    self.save(dkey, inp)
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

    def questionnaire_screen(self, dkey, string, scale_levels,
            questions, questions_per_page = 8,
            column_filler_width = 100, font_size = None,
            prompt_color = 'black'):
        init_wx()
        qd = QuestionnaireDialog(None, '', scale_levels,
            questions, questions_per_page, font_size,
            column_filler_width)
        prompt = self.text(0, .9, string,
            vAlign = 'top', wrap = 1.5, color = prompt_color)
        with self.timestamps(dkey):
            while True:
                self.draw(prompt)
                qd.CenterOnScreen(wx.BOTH)
                qd.ShowModal()
                responses = {}
                for q in qd.questions:
                    vs = [x.GetValue() for x in q['buttons']]
                    if not any(vs): break
                    responses[q['id']] = vs.index(True) + 1
                else:
                    for k, v in responses.items():
                        self.save(tuplecat(dkey, k), v)
                    qd.Destroy()
                    return
                self.draw(prompt)
                dialog = SchizoidDlg(title = 'Error')
                dialog.addText('')
                dialog.addText('Please answer all of the questions')
                dialog.addText('')
                dialog.show()

    def done(self, write_path, json_default = None):
    # We avoid self.save here in case we're inside a "with o.dkey_prefix".
        # Kill the trigger-code worker.
        if self.send_actiview_trigger_codes:
            self.trigger(standard_actiview_trigger_codes['STOP_LISTENING'])
            self.trigger_queue.put(PoisonPill)
            self.trigger_worker.join()
        # Save the time.
        if hasattr(self, 'clock'):
            self.data['overall_timing']['clock_duration'] = self.clock.getTime()
        self.data['overall_timing']['done'] = abs_timestamp_str()
        # Write the data to disk.
        with open(write_path, "w") as out:
            json.dump(self.data, out, sort_keys = True, indent = 2,
                default = json_default)
            print >>out

    #####################
    # Private
    #####################

    def save_timestamp(self, dkey, i):
        if not self.absolute_timestamps and not hasattr(self, 'clock'):
            self.start_clock()
        with self.dkey_prefix('times'):
            self.save(tuplecat(dkey, i),
                abs_timestamp_str()
                    if self.absolute_timestamps
                    else self.clock.getTime())

    def draw(self, *stimuli):
        for s in self.implicitly_draw: s.draw()
        for s in stimuli: s.draw()
        if self.double_draw:
            for s in self.implicitly_draw: s.draw()
            for s in stimuli: s.draw()
        self.win.flip()
