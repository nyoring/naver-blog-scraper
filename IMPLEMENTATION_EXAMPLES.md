# Naver Blog Scraping - Implementation Examples

## Quick Reference: Code Snippets from Production Scrapers

### 1. Search Results - Get Total Count

**From**: [snudm/naver-blog-crawler](https://github.com/snudm/naver-blog-crawler/blob/master/blog_query_crawler.py#L36-L43)

```python
from lxml import html
import requests

def get_nitems_for_query(query, sdate, edate):
    """Extract total post count from search results"""
    listurl = 'http://section.blog.naver.com/sub/SearchBlog.nhn?type=post&option.keyword=%s&term=&option.startDate=%s&option.endDate=%s&option.page.currentPage=%s&option.orderBy=date'
    
    try:
        root = html.parse(listurl % (query, sdate, edate, 1))
        # Extract from: <p class="several_post"><em>123건</em></p>
        nitems = root.xpath('//p[@class="several_post"]/em/text()')[0]
        return int(nitems.strip('건'))  # Remove Korean character
    except IOError:
        print(f'Error: ({query}, {sdate})')
        return 0

# Usage
total = get_nitems_for_query('파이썬', '2025-07-18', '2025-10-31')
print(f"Total posts: {total}")
```

---

### 2. Search Results - Extract Post Keys

**From**: [snudm/naver-blog-crawler](https://github.com/snudm/naver-blog-crawler/blob/master/blog_query_crawler.py#L103-L114)

```python
from lxml import html

def get_keys_from_page(query, date, pagenum):
    """Extract blogId, logNo, and date from search results page"""
    listurl = 'http://section.blog.naver.com/sub/SearchBlog.nhn?type=post&option.keyword=%s&term=&option.startDate=%s&option.endDate=%s&option.page.currentPage=%s&option.orderBy=date'
    
    root = html.parse(listurl % (query, date, date, pagenum))
    items = root.xpath('//ul[@class="list_type_1 search_list"]')[0]
    
    blog_ids = items.xpath('./input[@name="blogId"]/@value')
    log_nos = items.xpath('./input[@name="logNo"]/@value')
    times = items.xpath('./li/div[@class="list_data"]/span[@class="date"]/text()')
    
    return {(b, l): t for b, l, t in zip(blog_ids, log_nos, times)}

# Usage
keys = get_keys_from_page('파이썬', '2025-07-18', 1)
for (blog_id, log_no), date in keys.items():
    print(f"Blog: {blog_id}, Post: {log_no}, Date: {date}")
```

---

### 3. Handle iframe/frame Redirects

**From**: [KurtBestor/Hitomi-Downloader](https://github.com/KurtBestor/Hitomi-Downloader/blob/master/src/extractor/naver_downloader.py#L61-L79)

```python
from bs4 import BeautifulSoup
import requests
import re
from urllib.parse import urljoin

def read_page(url, session=None, depth=0):
    """Recursively resolve iframe/frame redirects"""
    if depth > 10:
        raise Exception('Too many redirects')
    
    if session is None:
        session = requests.Session()
    
    html = session.get(url).text
    
    # If response too small, likely a redirect page
    if len(html) < 5000:
        # Extract IDs and use mobile URL
        log_no_match = re.search(r'logNo=([0-9]+)', html)
        username_match = re.search(r'blog.naver.com/([0-9a-zA-Z]+)', url) or \
                        re.search(r'blogId=([0-9a-zA-Z]+)', html)
        
        if log_no_match and username_match:
            url = f'https://m.blog.naver.com/PostView.nhn?blogId={username_match.group(1)}&logNo={log_no_match.group(1)}&proxyReferer='
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # Check if we have the actual content
    if soup.find('div', {'id': 'viewTypeSelector'}):
        return url, soup
    
    # If still a frame, recursively follow it
    frame = soup.find('frame')
    if frame and frame.get('src'):
        return read_page(urljoin('https://blog.naver.com', frame['src']), session, depth + 1)
    
    return url, soup

# Usage
session = requests.Session()
final_url, soup = read_page('https://blog.naver.com/PostView.nhn?blogId=username&logNo=12345', session)
print(f"Final URL: {final_url}")
```

---

### 4. Extract Post Content

**From**: [snudm/naver-blog-crawler](https://github.com/snudm/naver-blog-crawler/blob/master/blog_text_crawler.py#L28-L63)

```python
from bs4 import BeautifulSoup
import requests

def extract_post_content(blog_id, log_no):
    """Extract post content and metadata"""
    url = f'http://m.blog.naver.com/{blog_id}/{log_no}'
    
    page = requests.get(url)
    soup = BeautifulSoup(page.text, 'html.parser')
    
    # Get content div
    content_div = soup.find('div', {'class': '_postView'})
    if not content_div:
        return None
    
    # Extract title
    title_elem = soup.find('h3', {'class': 'tit_h3'})
    title = title_elem.get_text().strip() if title_elem else None
    
    # Extract content
    content_html = str(content_div)
    content_text = content_div.get_text()
    
    # Extract category
    category_elem = soup.find('a', {'class': '_categoryName'})
    category = category_elem.get_text() if category_elem else None
    
    # Extract likes (sympathy count)
    sympathy_elem = soup.find('em', {'id': 'sympathyCount'})
    likes = int(sympathy_elem.get_text()) if sympathy_elem else 0
    
    return {
        'blog_id': blog_id,
        'log_no': log_no,
        'title': title,
        'content_html': content_html,
        'content_text': content_text,
        'category': category,
        'likes': likes,
        'url': url
    }

# Usage
post = extract_post_content('username', '12345')
print(f"Title: {post['title']}")
print(f"Likes: {post['likes']}")
```

---

### 5. Extract Images

**From**: [gallery-dl naverblog.py](https://github.com/mikf/gallery-dl/blob/master/gallery_dl/extractor/naverblog.py#L82-L87)

```python
from bs4 import BeautifulSoup
from urllib.parse import unquote

def extract_images(soup):
    """Extract image URLs from post content"""
    images = []
    
    # Method 1: data-lazy-src (lazy-loaded images)
    for img in soup.find_all('img', {'data-lazy-src': True}):
        url = img.get('data-lazy-src')
        if url:
            # Fix URL format
            url = url.replace('://post', '://blog', 1).split('?')[0]
            # Handle EUC-KR encoding
            if '\ufffd' in unquote(url):
                url = unquote(url, encoding='EUC-KR')
            images.append(url)
    
    # Method 2: span with _img class
    for span in soup.find_all('span', {'class': '_img'}):
        if 'thumburl' in span.attrs:
            images.append(span['thumburl'])
    
    return images

# Usage
images = extract_images(soup)
for img_url in images:
    print(f"Image: {img_url}")
```

---

### 6. Extract Videos

**From**: [gallery-dl naverblog.py](https://github.com/mikf/gallery-dl/blob/master/gallery_dl/extractor/naverblog.py#L89-L121)

```python
from bs4 import BeautifulSoup
import json
import requests

def extract_videos(soup):
    """Extract video metadata from post"""
    videos = []
    
    # Method 1: _naverVideo class
    for video in soup.find_all(class_='_naverVideo'):
        vid = video.get('vid')
        key = video.get('key')
        if vid and key:
            videos.append({'vid': vid, 'key': key, 'source': 'class'})
    
    # Method 2: __se_module_data script tags
    for script in soup.find_all('script', {'class': '__se_module_data'}):
        data_raw = script.get('data-module') or script.get('data-module-v2')
        if data_raw:
            try:
                data = json.loads(data_raw).get('data', {})
                if data.get('vid'):
                    videos.append({
                        'vid': data['vid'],
                        'key': data['inkey'],
                        'source': 'script'
                    })
            except:
                pass
    
    return videos

def get_video_url(vid, key):
    """Get actual video URL from Naver API"""
    url = f'https://apis.naver.com/rmcnmv/rmcnmv/vod/play/v2.0/{vid}?key={key}'
    
    try:
        response = requests.get(url)
        data = response.json()
        
        # Get highest quality
        videos = sorted(
            data.get('videos', {}).get('list', []),
            key=lambda v: v.get('size', 0),
            reverse=True
        )
        return videos[0]['source'] if videos else None
    except Exception as e:
        print(f"Error getting video URL: {e}")
        return None

# Usage
videos = extract_videos(soup)
for video in videos:
    video_url = get_video_url(video['vid'], video['key'])
    print(f"Video URL: {video_url}")
```

---

### 7. Extract Comments

**From**: [snudm/naver-blog-crawler](https://github.com/snudm/naver-blog-crawler/blob/master/blog_comment_crawler.py#L18-L56)

```python
from bs4 import BeautifulSoup
import requests
import re

def get_comments(blog_id, log_no):
    """Extract comments from post"""
    url = f'http://m.blog.naver.com/CommentList.nhn?blogId={blog_id}&logNo={log_no}'
    
    page = requests.get(url)
    soup = BeautifulSoup(page.text, 'html.parser')
    
    comments = []
    
    # Find all comment items
    for reply in soup.find_all('li', {'class': 'persc'}):
        comment = {}
        
        # Comment content
        p_tag = reply.find('p')
        if p_tag:
            comment['content'] = p_tag.get_text()
        
        # Comment date
        span_tag = reply.find('span')
        if span_tag:
            comment['date'] = span_tag.get_text()
        
        # Commenter blog ID
        dsc_id = reply.find('div', {'class': 'dsc_id'})
        if dsc_id and dsc_id.find('a'):
            href = dsc_id.find('a').get('href', '')
            match = re.search(r'blogId=([^&]+)', href)
            if match:
                comment['blogger_id'] = match.group(1)
        
        # Nested replies
        nested_replies = []
        for nested in reply.find_all('ul', {'class': 'lst_repl_sub'}):
            nested_reply = {}
            p = nested.find('p')
            if p:
                nested_reply['content'] = p.get_text()
            nested_replies.append(nested_reply)
        
        if nested_replies:
            comment['replies'] = nested_replies
        
        comments.append(comment)
    
    return comments

# Usage
comments = get_comments('username', '12345')
print(f"Total comments: {len(comments)}")
for comment in comments:
    print(f"- {comment['content']} ({comment['date']})")
```

---

### 8. Blog Post Listing API (Alternative)

**From**: [gallery-dl naverblog.py](https://github.com/mikf/gallery-dl/blob/master/gallery_dl/extractor/naverblog.py#L137-L173)

```python
from bs4 import BeautifulSoup
import requests
import re

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
        
        for post in data.get('postList', []):
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

# Usage
posts = get_blog_posts('username')
print(f"Total posts in blog: {len(posts)}")
for post in posts[:5]:
    print(f"- {post['title']} ({post['date']})")
```

---

## Complete Workflow Example

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
    
    def search_and_scrape(self, keyword: str, start_date: str, end_date: str, max_posts: int = 50):
        """Complete workflow: search -> scrape -> extract"""
        
        # Step 1: Get total count
        print(f"[1] Getting total count for '{keyword}'...")
        total = self._get_search_total_count(keyword, start_date, end_date)
        print(f"    Found {total} posts")
        
        # Step 2: Search and get post keys
        print(f"[2] Searching posts...")
        posts = self._search_posts(keyword, start_date, end_date, max_posts)
        print(f"    Retrieved {len(posts)} post keys")
        
        # Step 3: Scrape each post
        results = []
        for i, post_key in enumerate(posts, 1):
            print(f"[3.{i}] Scraping post {post_key['blog_id']}/{post_key['log_no']}...")
            
            try:
                post_data = self.get_post(post_key['blog_id'], post_key['log_no'])
                if post_data:
                    results.append(post_data)
                    print(f"      ✓ {post_data['title'][:50]}...")
                    print(f"      - Likes: {post_data['likes']}, Images: {len(post_data['images'])}")
            except Exception as e:
                print(f"      ✗ Error: {e}")
        
        return results
    
    def _get_search_total_count(self, keyword: str, start_date: str, end_date: str) -> int:
        """Get total post count"""
        url = (f'https://section.blog.naver.com/Search/Post.naver'
               f'?pageNo=1&rangeType=PERIOD&orderBy=recentdate'
               f'&startDate={start_date}&endDate={end_date}&keyword={keyword}')
        
        response = self._request(url)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        count_elem = soup.select_one('p.several_post em')
        if count_elem:
            count_text = count_elem.get_text().strip()
            return int(count_text.replace('건', ''))
        return 0
    
    def _search_posts(self, keyword: str, start_date: str, end_date: str, max_posts: int) -> List[Dict]:
        """Search posts and extract keys"""
        posts = []
        max_pages = (max_posts // 10) + 1
        
        for page in range(1, max_pages + 1):
            url = (f'https://section.blog.naver.com/Search/Post.naver'
                   f'?pageNo={page}&rangeType=PERIOD&orderBy=recentdate'
                   f'&startDate={start_date}&endDate={end_date}&keyword={keyword}')
            
            response = self._request(url)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            items = soup.select('ul.list_type_1.search_list li')
            if not items:
                break
            
            for item in items:
                if len(posts) >= max_posts:
                    break
                
                blog_id_input = item.select_one('input[name="blogId"]')
                log_no_input = item.select_one('input[name="logNo"]')
                
                if blog_id_input and log_no_input:
                    posts.append({
                        'blog_id': blog_id_input.get('value'),
                        'log_no': log_no_input.get('value'),
                    })
        
        return posts
    
    def get_post(self, blog_id: str, log_no: str) -> Optional[Dict]:
        """Get complete post data"""
        url = f'https://m.blog.naver.com/PostView.nhn?blogId={blog_id}&logNo={log_no}&proxyReferer='
        
        try:
            final_url, soup = self._resolve_iframe(url)
        except Exception as e:
            print(f'Error resolving iframe: {e}')
            return None
        
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
        
        return post_data
    
    def _resolve_iframe(self, url: str, depth: int = 0) -> tuple:
        """Resolve iframe/frame redirects"""
        if depth > 10:
            raise Exception('Too many redirects')
        
        response = self._request(url)
        html = response.text
        
        if len(html) < 5000:
            log_no = re.search(r'logNo=([0-9]+)', html)
            username = re.search(r'blog.naver.com/([0-9a-zA-Z]+)', url) or \
                      re.search(r'blogId=([0-9a-zA-Z]+)', html)
            
            if log_no and username:
                url = f'https://m.blog.naver.com/PostView.nhn?blogId={username.group(1)}&logNo={log_no.group(1)}&proxyReferer='
        
        soup = BeautifulSoup(html, 'html.parser')
        
        if soup.find('div', {'id': 'viewTypeSelector'}):
            return url, soup
        
        frame = soup.find('frame')
        if frame and frame.get('src'):
            return self._resolve_iframe(urljoin('https://blog.naver.com', frame['src']), depth + 1)
        
        return url, soup
    
    def _extract_images(self, soup) -> List[str]:
        """Extract image URLs"""
        images = []
        
        for img in soup.find_all('img', {'data-lazy-src': True}):
            url = img.get('data-lazy-src')
            if url:
                url = url.replace('://post', '://blog', 1).split('?')[0]
                if '\ufffd' in unquote(url):
                    url = unquote(url, encoding='EUC-KR')
                images.append(url)
        
        for span in soup.find_all('span', {'class': '_img'}):
            if 'thumburl' in span.attrs:
                images.append(span['thumburl'])
        
        return images
    
    def _extract_videos(self, soup) -> List[Dict]:
        """Extract video data"""
        videos = []
        
        for video in soup.find_all(class_='_naverVideo'):
            vid = video.get('vid')
            key = video.get('key')
            if vid and key:
                videos.append({'vid': vid, 'key': key})
        
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


# ===== USAGE =====

if __name__ == '__main__':
    scraper = NaverBlogScraper(delay=0.5)
    
    results = scraper.search_and_scrape(
        keyword='파이썬',
        start_date='2025-07-18',
        end_date='2025-10-31',
        max_posts=10
    )
    
    print(f"\n✓ Successfully scraped {len(results)} posts")
    
    # Save results
    import json
    with open('naver_blog_results.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
```

---

## Key Takeaways

| Feature | Implementation | Source |
|---------|---|---|
| **Search Total Count** | XPath: `//p[@class="several_post"]/em/text()` | snudm/naver-blog-crawler |
| **Post Keys** | Extract from hidden inputs: `input[name="blogId"]` | snudm/naver-blog-crawler |
| **iframe Handling** | Check response size < 5000, fallback to mobile URL | KurtBestor/Hitomi-Downloader |
| **Content Extraction** | `div#viewTypeSelector` | snudm/naver-blog-crawler |
| **Likes Count** | `em#sympathyCount` | snudm/naver-blog-crawler |
| **Images** | `img[data-lazy-src]` or `span._img[thumburl]` | gallery-dl |
| **Videos** | `script.__se_module_data[data-module-v2]` | gallery-dl |
| **Comments** | `li.persc` from CommentList.nhn | snudm/naver-blog-crawler |
| **Blog Posts API** | `PostViewBottomTitleListAsync.nhn` | gallery-dl |

