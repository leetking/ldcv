#!/usr/bin/env python
# only work in python3

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

DEBUG = True

options = None

def _D(fun = None, *args, **argv):
    if not DEBUG:
        return
    if callable(fun):
        fun(*args, **argv)
    else:
        print(fun, *args, **argv)


def strip(s):
    """Remove redundant space characters
    """
    return re.sub("[\s]+", ' ', s).strip() if isinstance(s, str) else ""


def parse_word_fams(wordfams):
    if wordfams is None:
        return []
    return list(set(word for word in wordfams.xpath(".//@title")))


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
            'example': [strip(''.join(example.itertext())), mp3(example)],
        } for example in sense.iterfind('.//span[@class="EXAMPLE"]'))

    ret = {
        # the smaller the more frequent, ordered by original page
        'freq': freq,
        # the opposite
        'opp': strip(''.join(x for x in _('.//span[@class="OPP"]').itertext()
                        if x not in ('OPP', 'SYN'))),
        # the synonym
        'syn': strip(''.join(x for x in _('.//span[@class="SYN"]').itertext()
                        if x not in ('OPP', 'SYN'))),
        # a short explanation
        'signpost': strip(_('.//span[@class="SIGNPOST"]').text),
        # countable or uncountable
        'attr': ''.join(filter(lambda x: x.strip() not in ('[', ']'),
                    _('.//span[@class="GRAM"]').itertext())),
        # the exact explanation
        'def': ''.join(_('.//span[@class="DEF"]').itertext()).strip(),
        # example sentences
        'examples': parse_examples(),
        # phrases maybe?
        'refs': list(x.strip() for x in re.split('[^ ()=/\'’\w-]+',
                    ''.join(_('.//span[@class="Crossref"]').itertext())) \
                        if x.strip() != ""),
    }
    return ret


def parse_entry(entry):
    def _(exp):
        EMPTY_ELEMENT = etree.Element('_')
        ret = entry.find(exp)
        return ret if ret is not None else EMPTY_ELEMENT

    def mp3(exp):
        src = entry.xpath(exp)
        return src[0].attrib['data-src-mp3'] if src else ""

    ret = {
        'pron': ''.join(_('.//span[@class="PronCodes"]').itertext()).strip(),
        'attr': strip(_('.//span[@class="POS"]').text),
        'audio-br': mp3('.//span[contains(@class, "brefile")]'),
        'audio-us': mp3('.//span[contains(@class, "amefile")]'),
        'senses': [parse_sense(sense, i+1) for i, sense in enumerate(entry.iterfind('.//span[@class="Sense"]'))]
    }
    return ret


def page_didyoumean(html, word):
    didyoumean = html.find('.//ul[@class="didyoumean"]')
    if didyoumean is None:
        return None
    return {
        'word': word,
        'suggestions': [x.text.strip() for x in didyoumean.iterfind('.//li/a')],
    }


def parse_word(html):
    """@html: etree.Element
    """
    word = {
        'word': html.find('.//h1[@class="pagetitle"]').text,
        'fams': parse_word_fams(html.find('.//div[@class="wordfams"]')),
        'entries': [parse_entry(entry) for entry in html.xpath('//span[@class="dictentry"]')],
    }

    return word


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
        colors = ''.join(cls.colors[x] for x in color.split(',') if x in cls.colors.keys())
        return "{0}{1}{2}".format(colors, s, cls.colors['default'])


class OrderedNumber:
    list_chars = {
        'number':      ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9',],
        'superscript': ['⁰', '¹', '²', '³', '⁴', '⁵', '⁶', '⁷', '⁸', '⁹',],
    }

    def __init__(self, _type='number'):
        self.chars = self.list_chars[_type] if _type in self.list_chars.keys() else self.list_chars['number']

    def __getitem__(self, no):
        return ''.join([self.chars[int(x)] for x in str(no)])


def arg_parse():
    parser = ArgumentParser(description = "LongMan Console Version")
    parser.add_argument('-f', '--full',
                        action = 'store_true',
                        default = False,
                        help = "print verbose explanations. "
                               "Default to print first three explanations")
    parser.add_argument('--color',
                        choices = ['always', 'auto', 'never'],
                        default = 'auto',
                        help = "colorize the output. "
                               'Default to "auto" or can be "never" or "always"')
    parser.add_argument('-j', '--json',
                        action = 'store_true',
                        default = False,
                        help = "dump the explanation with JSON style")
    parser.add_argument('words',
                        nargs = '*',
                        help = "words or quoted phrases to lookup")
    return parser.parse_args()


def format_out_explanation(word):
    """format explanation from dict and print it
    """
    _ = Colorizing.colorize
    EXAMPLE_MAX = 3

    print(_(word['word'], 'bold'))
    fams = word['fams']
    if fams:
        print("{0}: {1}".format(_("Word Families", 'yellow'), ", ".join(fams)))

    def sense_cmp(a, b):
        # the prior field is `signpost' then `freq'
        if a['signpost'] != '':
            if b['signpost'] != '':
                return (a['freq'] - b['freq'])
            else:
                return -1
        elif b['signpost'] != '':
            return 1
        else:
            return (a['freq'] - b['freq'])

    SUPER = OrderedNumber('superscript')
    for i, entry in enumerate(word['entries']):
        print("{0}{1} {2} {3}".format(word['word'], SUPER[i+1],
            _(entry['attr'], 'on_green'), _(entry['pron'], '')))
        for i, sense in enumerate(sorted(entry['senses'],
                            key=cmp_to_key(sense_cmp))):
            if options.full or sense['def'] != '':
                print(" {}. ".format(i+1), end='')
                if sense['attr'] != '':
                    print("[{}] ".format(_(sense['attr'], 'green')), end='')
                if sense['signpost'] != '':
                    print("{}  ".format(_(sense['signpost'].upper(), '~yellow')), end='')
                print("{} ".format(_(sense['def'], 'cyan')), end='')
                if sense['syn'] != '':
                    print('{}: {} '.format(_('SYN', '~yellow'), sense['syn'], end=''))
                if sense['opp'] != '':
                    print('{}: {} '.format(_('OPP', '~yellow'), sense['opp'], end=''))
                print('')
                for i, example in enumerate(sense['examples']):
                    if options.full or i < EXAMPLE_MAX:
                        print("     ➤ {1}".format(i+1, example['example'][0]))
                    else:
                        break
                if sense['refs']:
                    print(" » {0}".format(", ".join(sense['refs'])))
            else:
                break
        print('')


def format_out_suggestion(sugg):
    _ = Colorizing.colorize
    print('{0} {1}'.format(_(sugg['word'], 'bold'), _('not found', 'red')))
    print('{0} {1}'.format(_('Did you mean:', 'green'), ', '.join(sugg['suggestions'])))


def page_no_results(html):
    h1 = html.find('.//h1[@class="search_title"]')
    if h1 is None:
        return False
    title = "".join(h1.itertext()).lower()
    return ("sorry" in title and "no" in title)


def format_out_sorry_page(word):
    _ = Colorizing.colorize
    print('{0} {1}'.format(_("Sorry, there are no results for", 'red'), _(word, 'bold')))


def lookup_word(word):
    try:
        data = urlopen(URL.format(word))
    except IOError:
        print("Network is unavailable")
        return 1
    ctx = data.read().decode("utf-8")
    html = etree.HTML(ctx)
    suggestion = page_didyoumean(html, word)

    # the page `sorry' means that the word is random letters
    if page_no_results(html):
        format_out_sorry_page(word)
    # the page `didyoumean' means that the word you type doesn't exist
    elif suggestion is not None:
        format_out_suggestion(suggestion)
    else:
        word = parse_word(html)
        if options.json:
            print(json.dumps(word, ensure_ascii=False))
        else:
            format_out_explanation(word)

def interaction():
    """interactional mode
    """
    print('LongMan Console Version')
    try:
        import readline
    except ImportError:
        pass
    while True:
        try:
            word = input('> ').strip()
            if word in ('/full'):
                options.full = True
                print('verbose explanations on')
            elif word in ('/~full'):
                options.full = False
                print('verbose explanations off')
            elif word in ('/q', '/quit'):
                break
            else:
                lookup_word(word)
        except KeyboardInterrupt:
            print()
            continue
        except EOFError:
            break
    print("Bye")

def main():
    global options
    options = arg_parse()

    if options.words:
        for word in options.words:
            lookup_word(word)
    else:
        interaction()

if __name__ == '__main__':
    main()
