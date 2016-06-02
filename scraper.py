#!/usr/bin/env python3

import queue
import requests
import threading
import logging
import logging.handlers
import time
from colorlog import ColoredFormatter
from lxml import html


class PastebinScraper(object):
    def __init__(self, display_limit=100, paste_limit=0):
        # TODO: Resilient requests import
        # TODO: Requests status code and reason
        # TODO: DB connector
        self.display_limit = display_limit
        self.paste_limit = paste_limit
        self.unlimited_pastes = paste_limit == 0
        self.PB_LINK = 'http://pastebin.com/'
        self.pastes = queue.Queue(maxsize=8)
        self.pastes_seen = set()
        self.workers = 2

        # Init the logger
        self.logger = logging.getLogger('pastebin-scraper')
        self.logger.setLevel(logging.DEBUG)

        # Set up log rotation
        rotation = logging.handlers.RotatingFileHandler(
            filename='pastebin-scraper.log',
            maxBytes=2 * 1024 * 1024,
            backupCount=3
        )
        rotation.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s|%(levelname)-8s| %(message)s')
        rotation.setFormatter(formatter)
        self.logger.addHandler(rotation)

        console = logging.StreamHandler()
        console.setLevel(logging.INFO)
        formatter = ColoredFormatter(
            '%(log_color)s%(asctime)s|[%(levelname)-4s] %(message)s%(reset)s', '%H:%M:%S'
        )
        console.setFormatter(formatter)
        self.logger.addHandler(console)

    def _get_paste_data(self):
        paste_counter = 0
        self.logger.info('Unlimited pastes detected' if self.unlimited_pastes
                         else 'Paste limit: ' + str(self.paste_limit))
        while self.unlimited_pastes or (paste_counter < self.paste_limit):
            page = requests.get(self.PB_LINK)
            self.logger.debug('Got {} - {} from {}'.format(
                page.status_code,
                page.reason,
                self.PB_LINK
            ))
            tree = html.fromstring(page.content)
            pastes = tree.cssselect('ul.right_menu li')
            for paste in pastes:
                if not self.unlimited_pastes \
                   and (paste_counter >= self.paste_limit):
                    # Break for limits % 8 != 0
                    break
                name_link = paste.cssselect('a')[0]
                name = name_link.text_content()
                href = name_link.get('href')[1:]  # Get rid of leading /
                data = paste.cssselect('span')[0].text_content().split('|')
                language = None
                if len(data) == 2:
                    # Got language
                    language = data[0]
                paste_data = (name, language, href)
                self.logger.debug('Paste scraped: ' + str(paste_data))
                if paste_data[2] not in self.pastes_seen:
                    # New paste detected
                    self.logger.info('Scheduling new paste:' + str(paste_data))
                    self.pastes_seen.add(paste_data[2])
                    self.pastes.put(paste_data)
                    delay = 1  # random.randrange(1, 5)
                    time.sleep(delay)
                    paste_counter += 1
                    self.logger.debug('Paste counter now at ' + str(paste_counter))

    def _download_paste(self):
        while True:
            paste = self.pastes.get()  # (name, lang, href)
            data = requests.get(self.PB_LINK + 'raw/' + paste[2])
            if 'requesting a little bit too much' in data:
                print('Throttling...')
                self.pastes.put(paste)
                time.sleep(0.5)
            else:
                print(('Name: {name}\n'
                       'Language: {lang}\n'
                       'Link: {link}\n'
                       '{data}\n').format(
                    name=paste[0],
                    lang=paste[1],
                    link=self.PB_LINK + paste[2],
                    data=data.content.decode('utf-8')[:self.display_limit]
                ))

    def run(self):
        for i in range(self.workers):
            t = threading.Thread(target=self._download_paste)
            t.setDaemon(True)
            t.start()
        s = threading.Thread(target=self._get_paste_data)
        s.start()
        s.join()


if __name__ == '__main__':
    ps = PastebinScraper()
    ps.run()
