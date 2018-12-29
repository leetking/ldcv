============
ldcv |Build|
============

A console version LongMan_ dictionary.


Usage
-----

.. code-block:: text

   usage: ldcv [-h] [-f] [-j] [--cache CACHE] [-c CONFIG]
               [--color {always,auto,never}]
               [words [words ...]]

   LongMan Console Version

   positional arguments:
     words                 words or quoted phrases to lookup

   optional arguments:
     -h, --help            show this help message and exit
     -f, --full            print verbose explanations. Default to print first
                           three explanations
     -j, --json            dump the explanation with JSON style
     --cache CACHE         specify a word list file then cache words in it to
                           <cachefile>
     -c CONFIG, --config CONFIG
                           specify a config file
     --color {always,auto,never}
                           colorize the output. Default to "auto" or can be
                           "never" or "always"


Installation
------------

.. code-block:: shell

   $ pip install ldcv


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
.. |Build| image:: https://img.shields.io/badge/build_with-poetry-pink.svg?style=flat-square&logo=appveyor
   :target: https://github.com/sdispater/poetry
