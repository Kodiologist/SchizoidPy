SchizoidPy is a convenience library for using `PsychoPy`_ to do psychology experiments that aren't psychophysics experiments. It's like a GUI library for psychology. You create a ``schizoidpy.Task`` object and then call methods on it to solicit ratings on Likert-type scales, numbers typed into a textbox, and the like. Then you say ``task.done('data.json')`` to emit the current subject's responses and timing data as JSON.

You should take the absence of documentation as a hint that I'm not making any guarantees about stability. I wrote this thing for my own use. But see `Survivor`_ for an example task.

Also included in this repository is ``trigger-test.py``, a script for checking whether SchizoidPy's method of sending EEG trigger codes works on your system. It doesn't actually depend on SchizoidPy.

SchizoidPy began life as a spinoff of the generic functions in `Cookie`_.

SchizoidPy only works with Python 2. There's a ``python3`` branch, but it doesn't actually work, because it's written against wxPython 3, which is backwards-incompatible with wxPython 4, and wxPython 3 doesn't support Python 3. Moreover, wxPython 4 isn't compatible with pyglet, which is the only fully functional backend for PsychoPy as of this writing (11 Oct 2018).

License
============================================================

This program is copyright 2012–2018 Kodi Arfer.

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the `GNU General Public License`_ for more details.

.. _PsychoPy: http://psychopy.org/
.. _Survivor: https://github.com/Kodiologist/Survivor
.. _Cookie: https://github.com/Kodiologist/Cookie
.. _`GNU General Public License`: http://www.gnu.org/licenses/
