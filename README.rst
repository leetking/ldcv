====
ldcv
====

A console version LongMan_ dictionary.

Usage
-----

.. code-block:: text

   usage: ldcv [-h] [-f] [--color {always,auto,never}] [words [words ...]]

   LongMan Console Version

   positional arguments:
     words                 words or quoted phrases to lookup

   optional arguments:
     -h, --help            show this help message and exit
     -f, --full            print verbose explantions
     --color {always,auto,never}
                           colorize the output. Default to "auto" or can be
                           "never" or "always"

Installation
------------

.. code-block:: bash

   pip install ldcv

Enviroment or dependences
-------------------------
 - Python (3.x)
 - lxml_

Thanks
------

 - ydcv_

.. _LongMan: https://www.ldoceonline.com/
.. _ydcv: https://github.com/felixonmars/ydcv
.. _lxml: https://lxml.de/
