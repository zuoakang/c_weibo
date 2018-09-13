# !/usr/bin/env python3
# coding：utf-8

import re
import sys
import time
import logging
import grequests
from lxml import etree
from requests import Session
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from db import Mysql
from settings import WEIBO_URL, USERNAME

logger = logging.getLogger(__name__)


class WeiboComment(object):
    """查看某人在某微博的评论
        weibo_url指微博详情页的地址
        user指所查看用户的昵称
    """

    def __init__(self, weibo_url=WEIBO_URL, user=USERNAME):
        self.chrome_options = Options()
        self.chrome_options.add_argument("--headless")
        self.chrome_options.add_argument("--disable-gpu")
        self.driver = webdriver.Chrome(chrome_options=self.chrome_options)
        self.urls = []
        self.user = user
        self.weibo_url = weibo_url
        self.cookies = {}
        self.headers = {
            'user-agent': "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/57.0.2987.133 Safari/537.36",
            'accept-encoding': 'gzip, deflate, br',
            'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8'
        }

    def _base(self):
        self.driver.get(self.weibo_url)
        time.sleep(5)
        source = self.driver.page_source
        #logging.debug(source)
        _cookies = self.driver.get_cookies()
        for cookie in _cookies:
            self.cookies[cookie['name']] = cookie['value']
        self.driver.close()
        try:
            comments = int(re.findall(r'<em>(\d+)<', source)[0])
            if comments % 20 == 0:
                pages = comments // 20
            else:
                pages = comments // 20 + 1
        except IndexError as e:
            logger.error(f"no comments count\n{source}")
            sys.exit(1)
        try:
            weibo_id = re.findall(r'"id=(\d+)&amp;filter', source)[0]
        except IndexError as e:
            logger.error(f"no weibo id\n{source}")
            sys.exit(2)
        self.db = Mysql(weibo_id)
        self.db.create_table()
        logger.info(f'总共{pages}页,{comments}评论')
        for page in range(1, pages + 1):
            url = f'https://weibo.com/aj/v6/comment/big?ajwvr=6&id={weibo_id}&filter=all&page={page}'
            self.urls.append(url)

    @staticmethod
    def exception_handler(request, exception):
        logger.error(f"{exception}\n{request.url}")
        return None

    def getcomments(self):
        ss = Session()
        tasks = (grequests.get(url, session=ss, headers=self.headers, cookies=self.cookies, timeout=3) for url in self.urls)
        bs = grequests.map(tasks, size=10, exception_handler=self.exception_handler, gtimeout=3)
        for b in bs:
            if b:
                d = b.json()
                c_html = d['data']['html']
                c = etree.HTML(c_html.encode('unicode_escape'))
                uc = c.xpath('//div[@class="WB_text"]')
                for i in uc:
                    user, comment = i.xpath('string(.)').encode('utf-8').decode('unicode_escape').strip().split('：', maxsplit=1)
                    logger.debug(f'{bs.index(b) * 20 + uc.index(i) + 1}----------{user}:{comment}')
                    self.db.add(user, comment)
                    if user == self.user:
                        logger.info(f'{user}:{comment}')

    def run(self):
        self._base()
        self.getcomments()
        self.db.close()