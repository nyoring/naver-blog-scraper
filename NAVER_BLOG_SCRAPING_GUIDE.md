# Naver Blog Scraping: Complete Technical Guide

## Executive Summary

Based on analysis of production-grade scrapers (gallery-dl, Hitomi-Downloader, naver-blog-crawler), here are the key findings:

### Quick Answers to Your Questions

1. **Does Naver Blog use iframe for post content?** 
   - **YES** - Desktop version uses `<frame>` elements. Mobile version (`m.blog.naver.com`) has direct content in `<div id="viewTypeSelector">`
   - **Solution**: Use mobile URL as fallback when desktop returns frame

2. **Pagination structure & total count?**
   - Search results: Extract count from `<p class="several_post"><em>` text (e.g., "123건")
   - Pagination: Use `pageNo` parameter (1-indexed)
   - **API Alternative**: `PostViewBottomTitleListAsync.nhn` for blog post listing (more reliable)

3. **Anti-scraping measures?**
   - Moderate: User-Agent checking, rate limiting (~100-200ms delays recommended)
   - No JavaScript rendering required for basic content
   - Mobile version more lenient than desktop

4. **Best approach: Playwright vs HTTP?**
   - **Direct HTTP is sufficient** for most cases
   - Use mobile URL: `https://m.blog.naver.com/PostView.nhn?blogId={id}&logNo={logNo}`
   - Playwright only needed if: dynamic content, comment loading, or anti-bot detection

---

## Architecture Overview

### URL Patterns

```
# Desktop (has iframe issues)
https://blog.naver.com/PostView.nhn?blogId=USERNAME&logNo=POSTNUMBER
https://blog.naver.com/USERNAME/POSTNUMBER

# Mobile (RECOMMENDED - direct content)
https://m.blog.naver.com/PostView.nhn?blogId=USERNAME&logNo=POSTNUMBER

# Search Results
https://section.blog.naver.com/Search/Post.naver?pageNo=1&rangeType=PERIOD&orderBy=recentdate&startDate=2025-07-18&endDate=2025-10-31&keyword=KEYWORD

# Blog Post Listing API
https://blog.naver.com/PostViewBottomTitleListAsync.nhn
```

---

## Implementation Details

### 1. Search Results Scraping

**Source**: [snudm/naver-blog-crawler](https://github.com/snudm/naver-blog-crawler/blob/master/blog_query_crawler.py#L21-L40)

```python
# Get total post count
def get_nitems_for_query(query, sdate, edate):
    """Extract total post count from search results"""
    url = f'http://section.blog.naver.com/sub/SearchBlog.nhn?type=post&option.keyword={query}&term=&option.startDate={sdate}&option.endDate={edate}&option.page.currentPage=1&option.orderBy=date'
    
    root = html.parse(url)
    # Extract from: <p class="several_post"><em>123건</em></p>
    nitems = root.xpath('//p[@class="several_post"]/em/text()')[0]
    return int(nitems.strip('건'))  # Remove Korean character

# Get post keys from page
def get_keys_from_page(query, date, pagenum):
    """Extract blogId, logNo, and date from search results page"""
    url = f'http://section.blog.naver.com/sub/SearchBlog.nhn?type=post&option.keyword={query}&term=&option.startDate={date}&option.endDate={date}&option.page.currentPage={pagenum}&option.orderBy=date'
    
    root = html.parse(url)
    items = root.xpath('//ul[@class="list_type_1 search_list"]')[0]
    
    blog_ids = items.xpath('./input[@name="blogId"]/@value')
    log_nos = items.xpath('./input[@name="logNo"]/@value')
    times = items.xpath('./li/div[@class="list_data"]/span[@class="date"]/text()')
    
    return {(b, l): t for b, l, t in zip(blog_ids, log_nos, times)}
```

**Key Points**:
- Results show ~10 posts per page
- Total pages = `ceil(nitems / 10)`
- Extract `blogId` and `logNo` from hidden input fields
- Date format: "YYYY-MM-DD HH:MM"

---

### 2. Post Content Extraction

**Source**: [KurtBestor/Hitomi-Downloader](https://github.com/KurtBestor/Hitomi-Downloader/blob/master/src/extractor/naver_downloader.py#L61-L79)

#### Handle iframe/frame elements:

```python
def read_page(url, session, depth=0):
    """Recursively resolve iframe/frame redirects"""
    if depth > 10:
        raise Exception('Too deep')
    
    html = requests.get(url).text
    
    # If response is too small, likely a redirect page
    if len(html) < 5000:
        # Extract IDs and use mobile URL
        logNo = re.search(r'logNo=([0-9]+)', html).group(1)
        username = re.search(r'blog.naver.com/([0-9a-zA-Z]+)', url).group(1) or \
                   re.search(r'blogId=([0-9a-zA-Z]+)', url).group(1)
        url = f'https://m.blog.naver.com/PostView.nhn?blogId={username}&logNo={logNo}&proxyReferer='
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # Check if we have the actual content
    if soup.find('div', {'id': 'viewTypeSelector'}):
        return url, soup
    
    # If still a frame, recursively follow it
    frame = soup.find('frame')
    if frame:
        return read_page(urljoin('https://blog.naver.com', frame['src']), session, depth+1)
    
    return url, soup
```

#### Extract post metadata:

```python
def extract_post_data(soup, url):
    """Extract all post information"""
    
    # Title
    title = soup.find('meta', {'property': 'og:title'})['content'].strip()
    
    # Content (HTML)
    content_div = soup.find('div', {'id': 'viewTypeSelector'})
    content_html = str(content_div)
    content_text = content_div.get_text()
    
    # Author & Blog Name
    blog_id = re.search(r'blogId=([^&]+)', url).group(1)
    nick_name = soup.find('meta', {'property': 'og:url'})  # May need JS parsing
    
    # Date
    date_elem = soup.find('span', {'class': 'se_publishDate'}) or \
                soup.find('span', {'class': '_postAddDate'})
    date = date_elem.get_text() if date_elem else None
    
    # Likes (sympathyCount)
    sympathy = soup.find('em', {'id': 'sympathyCount'})
    likes = int(sympathy.get_text()) if sympathy else 0
    
    return {
        'title': title,
        'content_html': content_html,
        'content_text': content_text,
        'blog_id': blog_id,
        'date': date,
        'likes': likes,
        'url': url
    }
```

---

### 3. Extract Images & Videos

**Source**: [gallery-dl naverblog.py](https://github.com/mikf/gallery-dl/blob/master/gallery_dl/extractor/naverblog.py#L82-L121)

```python
def extract_images(soup):
    """Extract image URLs from post content"""
    images = []
    
    # Method 1: data-lazy-src (lazy-loaded images)
    for url in soup.find_all('img', {'data-lazy-src': True}):
        img_url = url.get('data-lazy-src')
        # Fix URL format
        img_url = img_url.replace('://post', '://blog', 1).split('?')[0]
        # Handle EUC-KR encoding
        if '\ufffd' in urllib.parse.unquote(img_url):
            img_url = urllib.parse.unquote(img_url, encoding='EUC-KR')
        images.append(img_url)
    
    # Method 2: span with _img class
    for span in soup.find_all('span', {'class': '_img'}):
        if 'thumburl' in span.attrs:
            images.append(span['thumburl'])
    
    return images

def extract_videos(soup):
    """Extract video URLs from post content"""
    videos = []
    
    # Method 1: _naverVideo class
    for video in soup.find_all(class_='_naverVideo'):
        vid = video.get('vid')
        key = video.get('key')
        if vid and key:
            videos.append({'vid': vid, 'key': key})
    
    # Method 2: __se_module_data script tags
    for script in soup.find_all('script', {'class': '__se_module_data'}):
        data_raw = script.get('data-module') or script.get('data-module-v2')
        if data_raw:
            try:
                data = json.loads(data_raw)['data']
                if data.get('vid'):
                    videos.append({'vid': data['vid'], 'key': data['inkey']})
            except:
                pass
    
    return videos

def get_video_url(vid, key):
    """Get actual video URL from Naver API"""
    url = f'https://apis.naver.com/rmcnmv/rmcnmv/vod/play/v2.0/{vid}?key={key}'
    response = requests.get(url)
    data = response.json()
    
    # Get highest quality
    videos = sorted(data['videos']['list'], key=lambda v: v.get('size', 0), reverse=True)
    return videos[0]['source'] if videos else None
```

---

### 4. Extract Comments

**Source**: [snudm/naver-blog-crawler](https://github.com/snudm/naver-blog-crawler/blob/master/blog_comment_crawler.py#L16-L56)

```python
def get_comments(blog_id, log_no):
    """Extract comments from post"""
    url = f'http://m.blog.naver.com/CommentList.nhn?blogId={blog_id}&logNo={log_no}'
    
    page = requests.get(url)
    soup = BeautifulSoup(page.text, 'html.parser')
    
    comments = []
    
    # Find all comment items
    for reply in soup.find_all('li', {'class': 'persc'}):
        comment_data = {}
        
        # Comment content
        p_tag = reply.find('p')
        if p_tag:
            comment_data['content'] = p_tag.get_text()
        
        # Comment date
        span_tag = reply.find('span')
        if span_tag:
            comment_data['date'] = span_tag.get_text()
        
        # Commenter blog ID
        dsc_id = reply.find('div', {'class': 'dsc_id'})
        if dsc_id and dsc_id.find('a'):
            href = dsc_id.find('a').get('href', '')
            blog_id_match = re.search(r'blogId=([^&]+)', href)
            if blog_id_match:
                comment_data['blogger_id'] = blog_id_match.group(1)
        
        # Nested replies
        nested_replies = []
        for nested in reply.find_all('ul', {'class': 'lst_repl_sub'}):
            # Same extraction logic for nested replies
            pass
        
        if nested_replies:
            comment_data['replies'] = nested_replies
        
        comments.append(comment_data)
    
    return comments
```

---

### 5. Blog Post Listing API (Alternative)

**Source**: [gallery-dl naverblog.py](https://github.com/mikf/gallery-dl/blob/master/gallery_dl/extractor/naverblog.py#L137-L173)

```python
def get_blog_posts(blog_id):
    """Get all posts from a blog using async API"""
    
    # First, get the first post number
    url = f'https://blog.naver.com/PostList.nhn?blogId={blog_id}'
    response = requests.get(url)
    
    # Extract first post number
    first_post = re.search(r'gnFirstLogNo = "(\d+)"', response.text)
    post_num = first_post.group(1) if first_post else '0'
    
    # Setup API parameters
    api_url = 'https://blog.naver.com/PostViewBottomTitleListAsync.nhn'
    params = {
        'blogId': blog_id,
        'logNo': post_num,
        'viewDate': '',
        'categoryNo': '',
        'parentCategoryNo': '',
        'showNextPage': 'true',
        'showPreviousPage': 'false',
        'sortDateInMilli': '',
        'isThumbnailViewType': 'false',
        'countPerPage': '',
    }
    
    all_posts = []
    
    while True:
        response = requests.get(api_url, params=params)
        data = response.json()
        
        for post in data['postList']:
            all_posts.append({
                'blogId': blog_id,
                'logNo': post['logNo'],
                'title': post.get('title'),
                'date': post.get('writeDate'),
                'url': f'https://blog.naver.com/PostView.nhn?blogId={blog_id}&logNo={post["logNo"]}'
            })
        
        # Check if there are more pages
        if not data.get('hasNextPage'):
            break
        
        # Update params for next page
        params['logNo'] = data['nextIndexLogNo']
        params['sortDateInMilli'] = data['nextIndexSortDate']
    
    return all_posts
```

---

## Complete Python Implementation

```python
import requests
from bs4 import BeautifulSoup
import re
import json
import time
from urllib.parse import urljoin, unquote
from typing import Dict, List, Optional

class NaverBlogScraper:
    def __init__(self, delay=0.5):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.delay = delay
    
    def _request(self, url, **kwargs):
        """Make request with delay"""
        time.sleep(self.delay)
        return self.session.get(url, **kwargs)
    
    # ===== SEARCH RESULTS =====
    
    def get_search_total_count(self, keyword: str, start_date: str, end_date: str) -> int:
        """Get total post count for search query"""
        url = (f'https://section.blog.naver.com/Search/Post.naver'
               f'?pageNo=1&rangeType=PERIOD&orderBy=recentdate'
               f'&startDate={start_date}&endDate={end_date}&keyword={keyword}')
        
        response = self._request(url)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find count element
        count_elem = soup.select_one('p.several_post em')
        if count_elem:
            count_text = count_elem.get_text().strip()
            return int(count_text.replace('건', ''))
        return 0
    
    def search_posts(self, keyword: str, start_date: str, end_date: str, 
                     max_pages: Optional[int] = None) -> List[Dict]:
        """Search posts by keyword and date range"""
        posts = []
        total_count = self.get_search_total_count(keyword, start_date, end_date)
        max_pages = max_pages or (total_count // 10 + 1)
        
        for page in range(1, max_pages + 1):
            url = (f'https://section.blog.naver.com/Search/Post.naver'
                   f'?pageNo={page}&rangeType=PERIOD&orderBy=recentdate'
                   f'&startDate={start_date}&endDate={end_date}&keyword={keyword}')
            
            response = self._request(url)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract post items
            items = soup.select('ul.list_type_1.search_list li')
            if not items:
                break
            
            for item in items:
                blog_id_input = item.select_one('input[name="blogId"]')
                log_no_input = item.select_one('input[name="logNo"]')
                date_elem = item.select_one('span.date')
                title_elem = item.select_one('a.post_title')
                
                if blog_id_input and log_no_input:
                    posts.append({
                        'blog_id': blog_id_input.get('value'),
                        'log_no': log_no_input.get('value'),
                        'date': date_elem.get_text() if date_elem else None,
                        'title': title_elem.get_text() if title_elem else None,
                        'url': f'https://blog.naver.com/PostView.nhn?blogId={blog_id_input.get("value")}&logNo={log_no_input.get("value")}'
                    })
        
        return posts
    
    # ===== POST CONTENT =====
    
    def _resolve_iframe(self, url: str, depth: int = 0) -> tuple:
        """Resolve iframe/frame redirects"""
        if depth > 10:
            raise Exception('Too many redirects')
        
        response = self._request(url)
        html = response.text
        
        # If response too small, likely a redirect
        if len(html) < 5000:
            log_no = re.search(r'logNo=([0-9]+)', html)
            username = re.search(r'blog.naver.com/([0-9a-zA-Z]+)', url) or \
                      re.search(r'blogId=([0-9a-zA-Z]+)', html)
            
            if log_no and username:
                url = f'https://m.blog.naver.com/PostView.nhn?blogId={username.group(1)}&logNo={log_no.group(1)}&proxyReferer='
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Check if we have content
        if soup.find('div', {'id': 'viewTypeSelector'}):
            return url, soup
        
        # Follow frame if exists
        frame = soup.find('frame')
        if frame and frame.get('src'):
            return self._resolve_iframe(urljoin('https://blog.naver.com', frame['src']), depth + 1)
        
        return url, soup
    
    def get_post(self, blog_id: str, log_no: str) -> Dict:
        """Get complete post data"""
        url = f'https://m.blog.naver.com/PostView.nhn?blogId={blog_id}&logNo={log_no}&proxyReferer='
        
        try:
            final_url, soup = self._resolve_iframe(url)
        except Exception as e:
            print(f'Error resolving iframe: {e}')
            return None
        
        # Extract metadata
        post_data = {
            'blog_id': blog_id,
            'log_no': log_no,
            'url': final_url,
        }
        
        # Title
        title_meta = soup.find('meta', {'property': 'og:title'})
        if title_meta:
            post_data['title'] = title_meta.get('content', '').strip()
        
        # Content
        content_div = soup.find('div', {'id': 'viewTypeSelector'})
        if content_div:
            post_data['content_html'] = str(content_div)
            post_data['content_text'] = content_div.get_text()
        
        # Date
        date_elem = soup.find('span', {'class': 'se_publishDate'}) or \
                   soup.find('span', {'class': '_postAddDate'})
        if date_elem:
            post_data['date'] = date_elem.get_text().strip()
        
        # Likes
        sympathy = soup.find('em', {'id': 'sympathyCount'})
        post_data['likes'] = int(sympathy.get_text()) if sympathy else 0
        
        # Images
        post_data['images'] = self._extract_images(soup)
        
        # Videos
        post_data['videos'] = self._extract_videos(soup)
        
        # Comments count (if available)
        comment_count = soup.find('em', {'id': 'commentCount'})
        post_data['comment_count'] = int(comment_count.get_text()) if comment_count else 0
        
        return post_data
    
    def _extract_images(self, soup) -> List[str]:
        """Extract image URLs"""
        images = []
        
        # Lazy-loaded images
        for img in soup.find_all('img', {'data-lazy-src': True}):
            url = img.get('data-lazy-src')
            if url:
                url = url.replace('://post', '://blog', 1).split('?')[0]
                if '\ufffd' in unquote(url):
                    url = unquote(url, encoding='EUC-KR')
                images.append(url)
        
        # Span images
        for span in soup.find_all('span', {'class': '_img'}):
            if 'thumburl' in span.attrs:
                images.append(span['thumburl'])
        
        return images
    
    def _extract_videos(self, soup) -> List[Dict]:
        """Extract video data"""
        videos = []
        
        # _naverVideo class
        for video in soup.find_all(class_='_naverVideo'):
            vid = video.get('vid')
            key = video.get('key')
            if vid and key:
                videos.append({'vid': vid, 'key': key})
        
        # __se_module_data scripts
        for script in soup.find_all('script', {'class': '__se_module_data'}):
            data_raw = script.get('data-module') or script.get('data-module-v2')
            if data_raw:
                try:
                    data = json.loads(data_raw).get('data', {})
                    if data.get('vid'):
                        videos.append({'vid': data['vid'], 'key': data['inkey']})
                except:
                    pass
        
        return videos
    
    def get_video_url(self, vid: str, key: str) -> Optional[str]:
        """Get actual video URL from Naver API"""
        url = f'https://apis.naver.com/rmcnmv/rmcnmv/vod/play/v2.0/{vid}?key={key}'
        
        try:
            response = self._request(url)
            data = response.json()
            videos = sorted(data.get('videos', {}).get('list', []), 
                          key=lambda v: v.get('size', 0), reverse=True)
            return videos[0]['source'] if videos else None
        except:
            return None
    
    # ===== COMMENTS =====
    
    def get_comments(self, blog_id: str, log_no: str) -> List[Dict]:
        """Get post comments"""
        url = f'https://m.blog.naver.com/CommentList.nhn?blogId={blog_id}&logNo={log_no}'
        
        response = self._request(url)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        comments = []
        for reply in soup.find_all('li', {'class': 'persc'}):
            comment = {}
            
            # Content
            p_tag = reply.find('p')
            if p_tag:
                comment['content'] = p_tag.get_text()
            
            # Date
            span_tag = reply.find('span')
            if span_tag:
                comment['date'] = span_tag.get_text()
            
            # Commenter
            dsc_id = reply.find('div', {'class': 'dsc_id'})
            if dsc_id and dsc_id.find('a'):
                href = dsc_id.find('a').get('href', '')
                match = re.search(r'blogId=([^&]+)', href)
                if match:
                    comment['blogger_id'] = match.group(1)
            
            comments.append(comment)
        
        return comments


# ===== USAGE EXAMPLE =====

if __name__ == '__main__':
    scraper = NaverBlogScraper(delay=0.5)
    
    # Search posts
    posts = scraper.search_posts(
        keyword='파이썬',
        start_date='2025-07-18',
        end_date='2025-10-31',
        max_pages=5
    )
    
    print(f'Found {len(posts)} posts')
    
    # Get first post details
    if posts:
        post = scraper.get_post(posts[0]['blog_id'], posts[0]['log_no'])
        print(f"Title: {post['title']}")
        print(f"Likes: {post['likes']}")
        print(f"Images: {len(post['images'])}")
        print(f"Videos: {len(post['videos'])}")
        
        # Get comments
        comments = scraper.get_comments(posts[0]['blog_id'], posts[0]['log_no'])
        print(f"Comments: {len(comments)}")
```

---

## Performance Recommendations

| Task | Method | Speed | Reliability |
|------|--------|-------|-------------|
| Search results | Direct HTTP | ⚡⚡⚡ | ⭐⭐⭐ |
| Post content | Mobile URL | ⚡⚡⭐ | ⭐⭐⭐ |
| Comments | Direct HTTP | ⚡⚡⭐ | ⭐⭐⭐ |
| Videos | API call | ⚡⭐⭐ | ⭐⭐⭐ |
| Dynamic content | Playwright | ⭐⭐⭐ | ⭐⭐⭐ |

---

## Anti-Scraping Mitigation

```python
# 1. Randomize delays
import random
delay = random.uniform(0.3, 1.0)

# 2. Rotate User-Agents
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
]
headers = {'User-Agent': random.choice(USER_AGENTS)}

# 3. Use session for cookies
session = requests.Session()

# 4. Add referer
headers['Referer'] = 'https://blog.naver.com/'

# 5. Respect robots.txt (check if exists)
# https://blog.naver.com/robots.txt
```

---

## Known Issues & Solutions

| Issue | Cause | Solution |
|-------|-------|----------|
| Empty content | Desktop iframe | Use mobile URL with fallback |
| EUC-KR encoding | Legacy encoding | Decode with `encoding='EUC-KR'` |
| Missing likes | Dynamic JS | Parse from `sympathyCount` element |
| Video extraction fails | API key changes | Use `data-module-v2` attribute |
| Rate limiting | Too fast requests | Add 500ms+ delay, rotate IPs |

---

## References

- **gallery-dl** (2025): https://github.com/mikf/gallery-dl/blob/master/gallery_dl/extractor/naverblog.py
- **Hitomi-Downloader**: https://github.com/KurtBestor/Hitomi-Downloader/blob/master/src/extractor/naver_downloader.py
- **naver-blog-crawler**: https://github.com/snudm/naver-blog-crawler/

