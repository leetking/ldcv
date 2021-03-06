#!/usr/bin/env python3

import sys
import re
import json
import os
import sqlite3
import socket

from itertools import count
from functools import cmp_to_key
from argparse import ArgumentParser
from configparser import ConfigParser
from pathlib import Path
from contextlib import closing
from urllib.error import URLError
from urllib.request import urlopen
from urllib.parse import quote

from lxml import etree

_VERSION = '2.0.4'

MAIN_URL = 'https://www.ldoceonline.com/dictionary/{0}'


class OptionAndConfig:
    """Save options from command line
       and the configs from config file if specify
    """
    quiet = False
    dbpath = '$HOME/.cache/ldcv/ldcv-cache.db3'
    threads_max = 20
    timeout = 7

    _HOME = os.getenv('HOME')
    _THREAD_MAX = 100
    _TIMEOUT = 10*60    # 10 minutes

    def __init__(self):
        self.dbpath = self.dbpath.replace('$HOME', self._HOME)


options = OptionAndConfig()

def strip(s):
    """Remove redundant space characters
    """
    return re.sub(r"[\s]+", ' ', s).strip() if isinstance(s, str) else ''


def parse_word_fams(wordfams):
    if wordfams is None:
        return []
    return list(set(word for word in wordfams.xpath(".//@title")))


def parse_sense(sense, freq=1):
    def _(exp):
        EMPTY_ELEMENT = etree.Element('_')
        eles = sense.find(exp)
        return eles if eles is not None else EMPTY_ELEMENT

    def parse_examples():
        def mp3(ent):
            src = ent.find('.//span[@data-src-mp3]')
            return src.attrib['data-src-mp3'] if src is not None else ''
        return list({
            'coll': ['', ''],
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
        'refs': list(x.strip() for x in re.split(r'[^ ()=/\'’\w-]+',
                    ''.join(_('.//span[@class="Crossref"]').itertext())) \
                        if x.strip() != ''),
    }
    return ret


def parse_entry(entry):
    def _(exp):
        EMPTY_ELEMENT = etree.Element('_')
        ret = entry.find(exp)
        return ret if ret is not None else EMPTY_ELEMENT

    def mp3(exp):
        src = entry.xpath(exp)
        return src[0].attrib['data-src-mp3'] if src else ''

    ret = {
        'pron': ''.join(_('.//span[@class="PronCodes"]').itertext()).strip(),
        'attr': strip(_('.//span[@class="POS"]').text),
        'audio-br': mp3('.//span[contains(@class, "brefile")]'),
        'audio-us': mp3('.//span[contains(@class, "amefile")]'),
        'senses': [parse_sense(sense, i) for i, sense in enumerate(entry.iterfind('.//span[@class="Sense"]'), 1)]
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
        colors = ''.join(cls.colors[x] for x in color.split(',') if x in cls.colors)
        return "{0}{1}{2}".format(colors, s, cls.colors['default'])


class OrderedNumber:
    list_chars = {
        'number':      ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9',],
        'superscript': ['⁰', '¹', '²', '³', '⁴', '⁵', '⁶', '⁷', '⁸', '⁹',],
    }

    def __init__(self, _type='number'):
        self.chars = self.list_chars[_type] if _type in self.list_chars else self.list_chars['number']

    def __getitem__(self, no):
        return ''.join([self.chars[int(x)] for x in str(no)])

class DbAdapter:
    def __init__(self, dbpath):
        # TODO support Windows
        # mkdir recursively the dbpath directory
        directory = os.path.dirname(dbpath)
        if not os.path.exists(directory):
            os.makedirs(directory)

        self._db = sqlite3.connect(dbpath)
        with closing(self._db.cursor()) as cur:
            cur.execute("""create table if not exists `words`(
                `word` text not null unique,
                `explanation` blob not null,
                primary key(`word`))""")
            self._db.commit()

    def __getitem__(self, word):
        if not isinstance(word, str):
            return None

        with closing(self._db.cursor()) as cur:
            cur.execute("select `explanation` from `words` where `word` = ?", (word,))
            exp = cur.fetchone()
        try:
            exp = json.loads(exp[0] if exp else None)
        except TypeError or json.decoder.JSONDecodeError:
            return None
        return exp

    def __setitem__(self, word, explanation):
        with closing(self._db.cursor()) as cur:
            cur.execute("insert into `words`(`word`,`explanation`) values(?, ?)",
                    (word, json.dumps(explanation, ensure_ascii=False)))
            self._db.commit()

    def get_all_cached_words(self):
        with closing(self._db.cursor()) as cur:
            cur.execute("select `word` from `words`")
            words = cur.fetchall()
            return (word[0] for word in words)

    def close(self):
        self._db.close()


def arg_parse():
    parser = ArgumentParser(prog='ldcv', description="LongMan Console Version")
    parser.add_argument('-f', '--full',
                        action='store_true',
                        default=False,
                        help="print verbose explanations. "
                             "Default to print first three explanations")
    parser.add_argument('-j', '--json',
                        action='store_true',
                        default=False,
                        help="dump the explanation with JSON style")
    parser.add_argument('--cache',
                        action='store',
                        help="specify a word list file then cache words from it to <cachefile>")
    parser.add_argument('--merge',
                        action='store',
                        help="specify other <cachefiles> so merge the word and explanation to this <cachefile>")
    parser.add_argument('-c', '--config',
                        action='store',
                        help="specify a config file")
    parser.add_argument('--color',
                        choices=['always', 'auto', 'never'],
                        default='auto',
                        help="colorize the output. "
                             'Default to "auto" or can be "never" or "always"')
    parser.add_argument('words',
                        nargs='*',
                        help="words or quoted phrases to lookup")
    return parser.parse_args(namespace=options)


def format_out_explanation(exp):
    """format explanation from dict and print it
    """
    # use in the inner for cache words
    if options.quiet:
        return

    if options.json:
        print(json.dumps(exp, ensure_ascii=False,indent=2, separators=(',', ': ')))
        return

    _ = Colorizing.colorize
    SENSE_MAX   = 7
    SENSE_MIN   = 3
    EXAMPLE_MAX = 3

    print(_(exp['word'], 'bold'))
    fams = exp['fams']
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
    for i, entry in enumerate(exp['entries'], 1):
        attr = ''
        if entry['attr'] != '':
            attr = " {} ".format(_(entry['attr'], 'green'))
        pron = entry['pron'] if entry['pron'] != '//' else ''
        print("{0}{1}{2}{3}".format(exp['word'], SUPER[i], attr, pron))
        for i, sense in enumerate(sorted(entry['senses'],
                            key=cmp_to_key(sense_cmp)), 1):
            if options.full or (sense['def'] != '' and i < SENSE_MAX) \
                    or (sense['def'] == '' and i < SENSE_MIN):
                print(" {}.".format(i), end='')
                if sense['attr'] != '':
                    print(" [{}]".format(_(sense['attr'], 'green')), end='')
                if sense['signpost'] != '':
                    print(" {} ".format(_(sense['signpost'].upper(), 'yellow')), end='')
                print(" {}".format(_(sense['def'], 'cyan')), end='')
                if sense['syn'] != '':
                    print(' {}: {}'.format(_('SYN', 'yellow'), sense['syn']), end='')
                if sense['opp'] != '':
                    print(' {}: {}'.format(_('OPP', 'yellow'), sense['opp']), end='')
                print('')
                for i, example in enumerate(sense['examples'], 1):
                    if options.full or i < EXAMPLE_MAX:
                        print("     ➤ {1}".format(i, example['example'][0]))
                    else:
                        break
                if sense['refs']:
                    print(" » {0}".format(", ".join(sense['refs'])))
            else:
                break
        print('')


def format_out_suggestion(sugg):
    # use in the inner for cache words
    if options.quiet:
        return
    _ = Colorizing.colorize
    print('{0} {1}'.format(_(sugg['word'], 'bold'), _('not found', 'red')))
    print('{0} {1}'.format(_('Did you mean:', 'green'), ', '.join(sugg['suggestions'])))


def page_no_results(html):
    h1 = html.find('.//h1[@class="search_title"]')
    if h1 is None:
        return False
    title = ''.join(h1.itertext()).lower()
    return ("sorry" in title and "no" in title)


def format_out_sorry_page(word):
    # use in the inner for cache words
    if options.quiet:
        return
    _ = Colorizing.colorize
    print('{0} {1}'.format(_("Sorry, there are no results for", 'red'), _(word, 'bold')))


def lookup_word(word):
    if os.path.exists(options.dbpath) \
            and not os.path.isfile(options.dbpath):
        print("dbcache file has existed at {} "
              "and isn't a regular file.".format(options.dbpath))
        return 1
    # prepare this word, maybe this is a feasible idea
    word = strip(word.lower()).replace(' ', '-')
    db = DbAdapter(options.dbpath)
    exp = db[word]
    if exp:
        format_out_explanation(exp)
        db.close()
        return 0

    try:
        data = urlopen(MAIN_URL.format(quote(word)), timeout=options.timeout)
    except socket.timeout:
        print("Network timed out in {}s".format(options.timeout))
        db.close()
        return 1
    except OSError:
        print("Network is unavailable")
        db.close()
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
        exp = parse_word(html)
        # cache this word
        db[word] = exp
        format_out_explanation(exp)
    db.close()
    return 0

def interaction():
    """interactional mode
    """
    print('LongMan Console Version. type /help to get help.')
    try:
        import readline
    except ImportError:
        pass
    while True:
        try:
            word = input('> ').strip()
            if word.startswith('/'):
                if word in ('/full'):
                    options.full = True
                    print('verbose explanations on')
                elif word in ('/!full', '/~full'):
                    options.full = False
                    print('verbose explanations off')
                elif word in ('/v', '/version'):
                    print('v{}'.format(_VERSION))
                elif word in ('/h', '/help'):
                    print('/full            turn on verbose explanation\n'
                          '/!full, /~full   turn off verbose explanation\n'
                          '/h, /help        show this page\n'
                          '/v, /version     show version\n'
                          '/q, /quit        exit programm')
                elif word in ('/q', '/quit'):
                    break
            elif word != '':
                lookup_word(word)
        except KeyboardInterrupt:
            print()
            continue
        except EOFError:
            break
    print("Bye")


def cache_words(wordsfile):
    from time import time
    from multiprocessing import Process

    threads_max = options.threads_max

    words = []
    with open(wordsfile) as cf:
        words = [strip(word) for line in cf for word in re.split('[,;|\n]+', line) if strip(word) != '']

    print("caching {} words with {} threads.".format(len(words), threads_max))
    options.quiet = True
    start = time()
    def thread_lookup_word(words):
        for w in words:
            lookup_word(w)
    portion_size = max(1, len(words) // threads_max)
    tasks = []
    for i in range(0, len(words), portion_size):
        ws = words[i:i+portion_size]
        if not ws:
            continue
        thread = Process(target=thread_lookup_word,
                    name="quering words({}~{})".format(i, i+portion_size), args=(ws,))
        thread.start()
        tasks.append(thread)
    for t in tasks:
        t.join()
    end = time()
    elapse = end-start
    print("cache {} word(s) and the total time "
            "is {:.2f}s, average time {:0.2f}/s with {} threads.".format(
              len(words), elapse, len(words)/elapse, threads_max))

def merge_db(otherdb):
    count = 0
    todb = DbAdapter(options.dbpath)
    fromdb = DbAdapter(otherdb)
    print(f"merge {otherdb} into dbcache locating at {options.dbpath} ...")
    for word in fromdb.get_all_cached_words():
        if not todb[word]:
            print(f"merge {word} into dbcache")
            todb[word] = fromdb[word]
            count += 1
    fromdb.close()
    todb.close()
    print(f"merge {otherdb} into dbcache over with amount of {count}")


def parse_config(config):
    """parse config file according to the order `/etc/ldcv/ldcvrc',
       `$HOME/.config/ldcv/ldcvrc', `./ldcvrc' and @config, and the later
       will overwrite the prevoius
    """
    global options
    RCLIST = ('/etc/ldcv/ldcvrc', options._HOME+'/.config/ldcv/ldcvrc',
            './ldcvrc', config or '')
    cfg = ConfigParser()
    for rc in RCLIST:
        if not os.path.isfile(rc):
            continue
        cfg.read(rc)
        # parse `main' section
        if 'main' in cfg and 'full' in cfg['main']:
            options.full = cfg['main'].getboolean('full')
        # parse `cache` section
        if 'cache' in cfg:
            cache = cfg['cache']
            if 'dbpath' in cache:
                path = cache['dbpath'].replace('$HOME', options._HOME)
                cwd = os.getcwd()
                # absolute path, evaluate directly
                if os.path.isabs(path):
                    options.dbpath = path
                # relative path, add prefix the current word directory
                else:
                    options.dbpath = os.path.join(cwd, path)
            if 'threads-max' in cache:
                # 2 ~ options._THREAD_MAX
                tmax = max(2, int(cache['threads-max']))
                options.threads_max = min(tmax, options._THREAD_MAX)
        # parse `net` section
        if 'net' in cfg:
            net = cfg['net']
            if 'timeout' in net:
                tout = max(3, int(net['timeout']))
                options.timeout = min(tout, options._TIMEOUT)


def main():
    global options
    options = arg_parse()

    parse_config(options.config)

    if options.cache:
        cache_words(options.cache)
    elif options.merge:
        merge_db(options.merge)
    elif options.words:
        for word in options.words:
            lookup_word(word)
    else:
        interaction()

if __name__ == '__main__':
    main()
