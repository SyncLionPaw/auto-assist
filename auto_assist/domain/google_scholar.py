from playwright.async_api import BrowserContext, TimeoutError
from bs4 import BeautifulSoup

from typing import List, TypedDict, Tuple, Dict
from urllib.parse import urlparse, urljoin
from datetime import datetime

import asyncio
import json
import sys
import os


from auto_assist.lib import get_logger, pending
from auto_assist.browser import BrowserCmd

logger = get_logger(__name__)


class Citation(TypedDict):
    type: str
    title: str
    authors: List[str]
    journal: str
    volume: str
    number: str
    pages: str
    year: str
    publisher: str


class GsProfileEntry(TypedDict):
    name: str
    url: str


class GsProfileItem(TypedDict):
    name: str
    url: str
    homepage: str
    brief: str
    cited_stats: str
    co_authors: List[GsProfileEntry]
    articles: List[str]
    tags: List[str]
    pdf_path: str
    html_path: str


class GsSearchItem(TypedDict):
    url: str
    citation: Citation
    profiles: List[GsProfileEntry]


async def gs_explore_profiles(browser: BrowserContext,
                              gs_profile_urls: List[str],
                              out_dir: str = './out',
                              depth_limit = 1,
                              google_scholar_url='https://scholar.google.com/',
                              order_by_year=True,
                              ):

    gs_pdf_dir = os.path.join(out_dir, 'gs_pdfs')
    gs_html_dir = os.path.join(out_dir, 'gs_htmls')
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(gs_pdf_dir, exist_ok=True)
    os.makedirs(gs_html_dir, exist_ok=True)

    gs_profiles_file = os.path.join(out_dir, 'gs_profiles.jsonl')

    # load existed data
    gs_profile_map: Dict[str, GsProfileItem] = {}
    if os.path.exists(gs_profiles_file):
        profile_list: List[GsProfileItem] = load_jsonl(gs_profiles_file)
        gs_profile_map = { gs_get_profile_id(profile['url']): profile for profile in profile_list }

    queue: List[Tuple[str, int]] = [ (url, 0) for url in gs_profile_urls ]

    gs_page = browser.pages[0]
    while len(queue) > 0:
        user_url, level = queue.pop(0)
        if level > depth_limit:
            break
        uid = gs_get_profile_id(user_url)
        if uid in gs_profile_map:
            logger.info("profile %s has been processed", user_url)
            co_authors = gs_profile_map[uid]['co_authors']
            queue.extend((author['url'], level+1) for author in co_authors)
            continue

        logger.info("process profile %s, level %d", user_url, level)

        open_url = urljoin(google_scholar_url, user_url)
        if order_by_year:
            open_url += '&view_op=list_works&sortby=pubdate'
        await gs_page.goto(open_url)

        profile = GsProfileItem()  # type: ignore
        profile['url'] = user_url
        profile['name'] = await gs_page.locator('div#gsc_prf_in').inner_text()
        profile['brief'] = await gs_page.locator('div#gsc_prf_w').inner_text()
        profile['cited_stats'] = await gs_page.locator('table#gsc_rsb_st').inner_text()
        try:
            profile['homepage'] = await gs_page.locator('a.gsc_prf_ila').get_by_text("Homepage").get_attribute('href', timeout=1e3)  # type: ignore
        except TimeoutError:
            profile['homepage'] = ''

        co_authors = []
        co_author_links = await gs_page.locator('ul.gsc_rsb_a li a').all()
        for co_author_link in co_author_links:
            name = await co_author_link.inner_text()
            url = await co_author_link.get_attribute('href')
            co_authors.append(GsProfileEntry(name=name, url=url)) # type: ignore
            queue.append((url, level+1))  # type: ignore

        articles = []
        article_links = await gs_page.locator('a.gsc_a_at').all()
        for article_link in article_links:
            articles.append(await article_link.inner_text())
        profile['articles'] = articles

        tags = []
        tag_links = await gs_page.locator('a.gsc_prf_inta.gs_ibl').all()
        for tag_link in tag_links:
            tags.append(await tag_link.inner_text())
        profile['tags'] = tags

        profile['co_authors'] = co_authors
        # save pdf
        pdf_path = os.path.join(gs_pdf_dir, f'profile_{uid}.pdf')
        await gs_page.pdf(path=pdf_path)
        profile['pdf_path'] = pdf_path
        # save html
        html_path = os.path.join(gs_html_dir, f'profile_{uid}.html')
        html_text = await gs_page.content()
        with open(html_path, 'w', encoding='utf-8') as fp:
            fp.write(html_text)
        profile['html_path'] = html_path
        # add to map to avoid duplicate processing
        gs_profile_map[uid] = profile

        # write result to file
        with open(gs_profiles_file, 'a', encoding='utf-8') as fp:
            fp.write(json.dumps(profile, ensure_ascii=False))
            fp.write('\n')


async def gs_search_by_authors(browser: BrowserContext,
                               authors: List[str],
                               out_dir: str = './out',
                               page_limit=3,
                               keyword='',
                               google_scholar_url='https://scholar.google.com/?hl=en&as_sdt=0,5',
                               ):
    """
    search by authors in google scholar
    """
    os.makedirs(out_dir, exist_ok=True)
    gs_result_file = os.path.join(out_dir, 'gs_result.jsonl')

    # load existed results
    gs_search_result = []
    if os.path.exists(gs_result_file):
        gs_search_result: List[GsSearchItem] = load_jsonl(gs_result_file)

    processed_articles = set(item['url'] for item in gs_search_result)

    gs_page = browser.pages[0]
    for author in authors:
        # search articles by auther
        await gs_page.goto(google_scholar_url)
        search_input = f'author:"{author}"'
        if keyword:
            search_input += f' {keyword}'
        await gs_page.locator('input#gs_hdr_tsi').fill(search_input)
        await gs_page.locator('input#gs_hdr_tsi').press('Enter')

        for i_page in range(page_limit):
            if i_page > 0:
                try:
                    await gs_page.locator('td[align="left"]').click(timeout=10e3)
                except TimeoutError:
                    logger.warn('no more page to process')
                    break

            # iterate each article in google scholar,
            cite_modal = gs_page.locator('div#gs_cit')

            article_divs = await gs_page.locator('div.gs_r.gs_or.gs_scl').all()
            for article_div in article_divs:
                try:
                    article_url = await article_div.locator('h3.gs_rt a').get_attribute('href', timeout=1e3)
                    if article_url in processed_articles:
                        logger.info('article %s has been processed', article_url)
                        continue

                    # download and parse endnote citation
                    await article_div.locator('a.gs_or_cit').click()

                    async with gs_page.expect_download() as download_info:
                        await cite_modal.locator('a.gs_citi').get_by_text('EndNote').click()
                    download = await download_info.value
                    # close cite modal
                    await cite_modal.locator('a#gs_cit-x').click()

                    await download.save_as(download.suggested_filename)
                    with open(download.suggested_filename, 'r', encoding='utf-8') as fp:
                        cite_data = fp.read()

                    citation = parse_endnote(cite_data)
                    logger.info('citation: %s', citation)

                    # get authors with google scholar and the link to their profile
                    profile_links = await article_div.locator('div.gs_a a').all()
                    gs_profiles = []
                    for profile_link in profile_links:
                        gs_profile = GsProfileEntry()  # type: ignore
                        gs_profile['name'] = await profile_link.inner_text()
                        gs_profile['url'] = await profile_link.get_attribute('href')  # type: ignore
                        logger.info('gs_profile: %s', gs_profile)
                        gs_profiles.append(gs_profile)

                    gs_search_item = GsSearchItem(
                        url=article_url,  # type: ignore
                        citation=citation,
                        profiles=gs_profiles,
                    )
                    gs_search_result.append(gs_search_item)

                    # write result to file
                    with open(gs_result_file, 'a', encoding='utf-8') as fp:
                        fp.write(json.dumps(gs_search_item, ensure_ascii=False))
                        fp.write('\n')

                    processed_articles.add(article_url)  # type: ignore

                except TimeoutError as e:
                    logger.exception("unexpected error occured")


def gs_list_profile_urls(result_file: str):
    result: List[GsSearchItem] = load_jsonl(result_file)
    urls = set(profile['url'] for item in result for profile in item['profiles'])
    print('\n'.join(urls))


def gs_list_authors(result_file: str):
    from colorama import deinit
    deinit()
    result: List[GsSearchItem] = load_jsonl(result_file)
    names = set(author for item in result for author in item['citation']['authors'])
    print('\n'.join(names))


def gs_get_profile_id(url: str):
    # parse url and get user from query string
    query = urlparse(url).query
    params = dict(kv.split('=') for kv in query.split('&'))
    return params['user']

def gs_fix_profile_from_html(out_dir: str, suffix = None):
    if suffix is None:
        # use timestemp as suffix
        suffix = datetime.now().strftime('%Y%m%d%H%M%S')

    gs_html_dir = os.path.join(out_dir, 'gs_htmls')
    src = os.path.join(out_dir, 'gs_profiles.jsonl')
    dst = os.path.join(out_dir, f'gs_profiles_{suffix}.jsonl')

    profiles: List[GsProfileItem] = load_jsonl(src)
    for profile in profiles:
        # fix co_authors name
        for co_author in profile['co_authors']:
            if isinstance(co_author['name'], list):
                co_author['name'] = co_author['name'][0]
        # fix data from html
        html_path = os.path.join(gs_html_dir, os.path.basename(profile['html_path']))
        with open(html_path, 'r', encoding='utf-8') as fp:
            soup = BeautifulSoup(fp, 'html.parser')
        # get article from html
        article_links = soup.select('a.gsc_a_at')
        articles = [article_div.text for article_div in article_links]
        profile['articles'] = articles
        # get tags from html
        tags_links = soup.select('a.gsc_prf_inta.gs_ibl')
        tags = [tag_div.text for tag_div in tags_links]
        profile['tags'] = tags

    with open(dst, 'w', encoding='utf-8') as fp:
        for profile in profiles:
            fp.write(json.dumps(profile, ensure_ascii=False))
            fp.write('\n')


def load_jsonl(file: str):
    result = []
    with open(file, 'r', encoding='utf-8') as fp:
        for line in fp:
            result.append(json.loads(line))
    return result


def parse_endnote(text: str):
    """
    Parse EndNote citation to python dict data
    Example of EndNote citation:

    %0 Journal Article
    %T Theoretical studies on anatase and less common TiO2 phases: bulk, surfaces, and nanomaterials
    %A De Angelis, Filippo
    %A Di Valentin, Cristiana
    %A Fantacci, Simona
    %A Vittadini, Andrea
    %A Selloni, Annabella
    %J Chemical reviews
    %V 114
    %N 19
    %P 9708-9753
    %@ 0009-2665
    %D 2014
    %I ACS Publications
    """

    citation = Citation()  # type: ignore
    citation['authors'] = []
    for line in text.splitlines():
        if line.startswith('%'):
            key, value = line[1:].split(' ', 1)
            if key == '0':
                citation['type'] = value
            elif key == 'T':
                citation['title'] = value.strip()
            elif key == 'A':
                citation['authors'].append(value.strip())
            elif key == 'J':
                citation['journal'] = value
            elif key == 'V':
                citation['volume'] = value
            elif key == 'N':
                citation['number'] = value
            elif key == 'P':
                citation['pages'] = value
            elif key == 'D':
                citation['year'] = value
            elif key == 'I':
                citation['publisher'] = value
    return citation


class GsCmd:

    def __init__(self, browser_dir) -> None:
        self._browser_dir = browser_dir

    def gs_search_by_authors(self,
                             out_dir: str = './out',
                             page_limit=3,
                             keyword='',
                             google_scholar_url='https://scholar.google.com/?hl=en&as_sdt=0,5',
                             ):
        authors = [line.strip() for line in sys.stdin]
        async def run():
            async with BrowserCmd()._launch_async(self._browser_dir) as browser_ctx:
                await gs_search_by_authors(
                    browser_ctx, authors=authors, out_dir=out_dir, keyword=keyword, page_limit=page_limit, google_scholar_url=google_scholar_url)
                pending()
        asyncio.run(run())

    def gs_explore_profiles(self,
                            out_dir: str = './out',
                            depth_limit=1,
                            google_scholar_url='https://scholar.google.com/',
                            order_by_year=True,
                            ):
        profile_urls = [line.strip() for line in sys.stdin]
        async def run():
            async with BrowserCmd()._launch_async(self._browser_dir) as browser_ctx:
                await gs_explore_profiles(
                    browser_ctx, gs_profile_urls=profile_urls, out_dir=out_dir, depth_limit=depth_limit, order_by_year=order_by_year, google_scholar_url=google_scholar_url,
                )
                pending()
        asyncio.run(run())


    def gs_list_profile_urls(self, result_file: str):
        gs_list_profile_urls(result_file)


    def gs_list_authors(self, result_file: str):
        gs_list_authors(result_file)


    def gs_fix_profile_from_html(self, out_dir: str, suffix = None):
        gs_fix_profile_from_html(out_dir, suffix)
