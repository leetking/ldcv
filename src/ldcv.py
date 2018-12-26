#!/usr/bin/env python
# just work in python3

import sys
from sys import argv
from urllib.request import urlopen
from html.parser import HTMLParser
from lxml import etree
from itertools import count
from argparse import ArgumentParser
from functools import cmp_to_key

import re
import json

URL = 'https://www.ldoceonline.com/dictionary/{0}'

options = None

def _D(fun = None, *args, **argv):
    if not DEBUG:
        return
    if callable(fun):
        fun(*args, **argv)
    else:
        print(fun, *args, **argv)

def strip(s):
    """Remove redundant space characters"""
    return re.sub("[\s]+", ' ', s).strip() if s is not None else ""

def parse_word_fams(wordfams):
    if wordfams is None:
        return []
    return list({word for word in wordfams.xpath(".//@title")})

def parse_sense(sense, freq = 1):
    def _(exp):
        EMPTY_ELEMENT = etree.Element('_')
        eles = sense.find(exp)
        return eles if eles is not None else EMPTY_ELEMENT
    def parse_examples():
        def mp3(ent):
            src = ent.find('.//span[@data-src-mp3]')
            return src.attrib['data-src-mp3'] if src is not None else ""
        return list({
                'coll': ["", ""],
                'example': [strip("".join(example.itertext())), mp3(example)],
            } for example in sense.iterfind('.//span[@class="EXAMPLE"]'))

    ret = {
        'freq': freq,                     # the smaller the more frequent, ordered by original page
        'opp': strip(_('.//span[@class="OPP"]').text),
        'syn': strip(_('.//span[@class="SYN"]').text),
        'signpost': strip(_('.//span[@class="SIGNPOST"]').text),
        'attr': "".join(filter(lambda x: x.strip() not in ('[', ']'),
                _('.//span[@class="GRAM"]').itertext())),
        'def': "".join(_('.//span[@class="DEF"]').itertext()).strip(),
        'examples': parse_examples(),
        'refs': list(filter(lambda x: len(x) is not 0,
                    [x.strip() for x in re.split('[^ ()=/\'’\w-]+',
                        "".join(_('.//span[@class="Crossref"]').itertext()))])),
    }
    return ret

def parse_entry(entry):
    def _(exp):
        EMPTY_ELEMENT = etree.Element('_')
        ret = entry.find(exp)
        return ret if ret is not None else EMPTY_ELEMENT
    def mp3(exp):
        src = entry.find(exp)
        return src.attrib['data-src-mp3'] if src is not None else ""

    return {'pron': "".join(_('.//span[@class="PronCodes"]').itertext()).strip(),
            'attr': strip(_('.//span[@class="POS"]').text),
            #'audio-br': _('.//span[contains(@class, "brefile")]'),
            #'audio-us': mp3('.//span[contains(@class, "amefile")]'),
            'senses': [parse_sense(*sense) for sense in zip(entry.iterfind('.//span[@class="Sense"]'), count(1))]}

def is_page_didyoumean(html):
    pass

def parse_word(html):
    """
    @html: etree.Element
    """
    word = {
        'word': html.find('.//h1[@class="pagetitle"]').text,
        'fams': parse_word_fams(html.find('.//div[@class="wordfams"]')),
        'entries': [parse_entry(entry) for entry in html.xpath('//span[@class="dictentry"]')],
    }

    return word

class Explanation:
    pass

class Colorizing:
    colors = {
        'none': "",
        'default':   "\033[0m",
        'bold':      "\033[1m",
        'underline': "\033[4m",
        'blink':     "\033[5m",
        'reverse':   "\033[7m",
        'concealed': "\033[8m",

        'black':   "\033[30m",
        'red':     "\033[31m",
        'green':   "\033[32m",
        'yellow':  "\033[33m",
        'blue':    "\033[34m",
        'magenta': "\033[35m",
        'cyan':    "\033[36m",
        'white':   "\033[37m",

        'on_black':   "\033[40m",
        'on_red':     "\033[41m",
        'on_green':   "\033[42m",
        'on_yellow':  "\033[43m",
        'on_blue':    "\033[44m",
        'on_magenta': "\033[45m",
        'on_cyan':    "\033[46m",
        'on_white':   "\033[47m",

        # ~color: the background color is `color'
        #         and text color is reversal `color'
        '~black':  "\033[40m\033[37m",
        '~red':    "\033[41m\033[36m",
        '~green':  "\033[42m\033[35m",
        '~yellow': "\033[43m\033[34m",
        '~blue':   "\033[44m\033[33m",
        '~magenta':"\033[45m\033[32m",
        '~cyan':   "\033[46m\033[31m",
        '~white':  "\033[47m\033[30m",

        'beep': "\007",
    }

    @classmethod
    def colorize(cls, s, color=None):
        if options.color == 'never':
            return s
        if options.color == 'auto' and not sys.stdout.isatty():
            return s
        if color is None:
            return s
        colors = "".join([cls.colors[x] for x in
                    filter(lambda i: i in cls.colors, list(color.split(',')))])
        return "{0}{1}{2}".format(colors, s, cls.colors['default'])


def arg_parse():
    parser = ArgumentParser(description = "LongMan Console Version")
    parser.add_argument('-f', '--full',
                        action = 'store_true',
                        default = False,
                        help = "print verbose explantions")
    parser.add_argument('--color',
                        choices = ['always', 'auto', 'never'],
                        default = 'auto',
                        help = "colorize the output. "
                               'Default to "auto" or can be "never" or "always"')
    parser.add_argument('words',
                        nargs = '*',
                        help = "words or quoted phrases to lookup")
    return parser.parse_args()

def format_out_explanation(word):
    """format explantion from dict and print it"""
    _ = Colorizing.colorize
    print(_(word['word'], 'bold'))
    if word['fams'] is not "":
        fams = word['fams']
        print("{0}: {1}".format(_("FAMILY", 'yellow'), ", ".join(fams)))
    SUPER = ['⁰', '¹', '²', '³', '⁴', '⁵', '⁶', '⁷', '⁸', '⁹',]
    ROMAN = [],
    def sense_cmp(a, b):
        if a['signpost'] is not "":
            if b['signpost'] is not "":
                return (a['freq'] - b['freq'])
            else:
                return -1
        elif b['signpost'] is not "":
            return 1
        else:
            return (a['freq'] - b['freq'])

    for i, entry in zip(count(1), word['entries']):
        print("{0}{1} {2} {3}".format(word['word'], SUPER[i%10], entry['attr'], entry['pron']))
        for i, sense in zip(count(1), sorted(entry['senses'], key=cmp_to_key(sense_cmp))):
            print(" {0}. {1} {2}".format(i, _(sense['signpost'].upper(), '~yellow'), sense['def']))
            for k, example in zip(count(1), sense['examples']):
                #print(" {0} {1} (={2})".format(k, example['coll'][0], example['coll'][1]))
                print("     + {1}".format(i, example['example'][0]))
            print(" -> {0}".format(", ".join(sense['refs'])))

def lookup_word(word):
    try:
        data = urlopen(URL.format(word))
    except IOError:
        print("Network is unavailable")
        return 1
    ctx = data.read().decode("utf-8")
    html = etree.HTML(ctx)
    word = parse_word(html)
    format_out_explanation(word)

def main():
    global options
    options = arg_parse()

    if options.words:
        for word in options.words:
            lookup_word(word)
    
if __name__ == '__main__':
    main()
